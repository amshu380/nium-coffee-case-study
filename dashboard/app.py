import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db_utils import run_query

st.set_page_config(
    page_title="ACME Baristas - Global Market Analysis",
    page_icon=":coffee:",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }
    .stMetric {
        background: linear-gradient(180deg, #fffaf3 0%, #f4ead9 100%);
        border: 1px solid #dbc4a1;
        padding: 1rem;
        border-radius: 16px;
        box-shadow: 0 10px 30px rgba(96, 62, 31, 0.08);
    }
    .hero-card {
        background: linear-gradient(135deg, #2f5d50 0%, #14342d 100%);
        color: #f8f1e5;
        padding: 1.25rem 1.5rem;
        border-radius: 20px;
        margin-bottom: 1rem;
    }
    .insight-card {
        background: #fffdf8;
        border-left: 4px solid #c9822b;
        padding: 0.9rem 1rem;
        border-radius: 12px;
        margin: 0.6rem 0;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.title("ACME Baristas: Global Market Entry Analysis")
st.markdown("**Recommendation engine for selecting 3 launch markets** | Data: USDA PSD Coffee, World Bank Population, ISO Country Codes")
st.markdown(
    """
    <div class='hero-card'>
        <h3 style='margin:0 0 0.4rem 0;'>Decision framing</h3>
        <div>Use the tabs to move from global momentum, to market screening, to country-level evidence, and finally the recommendation logic behind the top three launch markets.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.header("Filters & Controls")
st.sidebar.caption("Each control affects specific tabs as noted below.")

st.sidebar.markdown("---")

# Year range filter
years_df = run_query("SELECT DISTINCT market_year FROM analytics.fact_coffee ORDER BY market_year")
min_year = int(years_df["market_year"].min())
max_year = int(years_df["market_year"].max())
selected_year_range = st.sidebar.slider("Year range", min_year, max_year, (max(2015, min_year), max_year))
st.sidebar.caption("Affects: Global Overview tab KPI cards, trend chart, and regional distribution chart.")

st.sidebar.markdown("---")

# Region filter
regions_df = run_query("SELECT DISTINCT region FROM analytics.dim_country WHERE region IS NOT NULL ORDER BY region")
all_regions = regions_df["region"].tolist()
selected_regions = st.sidebar.multiselect("Regions", all_regions, default=all_regions)
st.sidebar.caption("Affects: Recommendation tab ranking and Market Comparison tab scatter/map.")

st.sidebar.markdown("---")

st.sidebar.markdown("### Composite Score Weights")
st.sidebar.caption("Affects: Recommendation tab only. Adjust to stress-test the ranking under different strategic priorities.")
w_size = st.sidebar.slider("Market size", 0.0, 1.0, 0.35, 0.05)
w_growth = st.sidebar.slider("Growth rate", 0.0, 1.0, 0.30, 0.05)
w_pop = st.sidebar.slider("Population", 0.0, 1.0, 0.20, 0.05)
w_import = st.sidebar.slider("Import openness", 0.0, 1.0, 0.15, 0.05)
total_w = w_size + w_growth + w_pop + w_import
if total_w > 0:
    w_size, w_growth, w_pop, w_import = [w / total_w for w in (w_size, w_growth, w_pop, w_import)]
st.sidebar.caption(f"Weights auto-normalized to sum to 1.0")

st.sidebar.markdown("---")
st.sidebar.caption("Country selector on the Country Deep Dive tab is independent of these filters.")


def sql_in_list(values: list[str]) -> str:
    return ','.join(["'" + value.replace("'", "''") + "'" for value in values])


def pct_label(value):
    if pd.isna(value):
        return "N/A"
    return f"{value * 100:.1f}%"


def pop_label(value):
    if pd.isna(value):
        return "N/A"
    return f"{value / 1e6:.0f}M"


def num_label(value, decimals=0):
    if pd.isna(value):
        return "N/A"
    return f"{value:,.{decimals}f}"


def narrative_for_country(row: pd.Series, rank: int) -> str:
    pieces = []
    if rank == 1:
        pieces.append("Scale leader with a strong blend of size and trajectory.")
    elif rank == 2:
        pieces.append("High-upside market with strong forward demand signal.")
    else:
        pieces.append("Attractive demand story with clear strategic trade-offs to manage.")
    if pd.notna(row.get("consumption_cagr_5y")):
        pieces.append(f"5Y CAGR at {row['consumption_cagr_5y'] * 100:.1f}%.")
    if pd.notna(row.get("import_dependency_ratio")):
        pieces.append(f"Import dependency near {row['import_dependency_ratio'] * 100:.0f}%.")
    return " ".join(pieces)


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Recommendation",
    "Global Overview",
    "Market Comparison",
    "Country Deep Dive",
    "Methodology",
])

with tab1:
    st.header("Top 3 Markets for ACME Baristas")

    if not selected_regions:
        st.warning("Select at least one region to view recommendations.")
    else:
        region_clause = f"AND region IN ({sql_in_list(selected_regions)})"

        score_query = f"""
        WITH base AS (
            SELECT * FROM analytics.v_latest_year_snapshot
            WHERE domestic_consumption IS NOT NULL AND population IS NOT NULL AND domestic_consumption > 0
            {region_clause}
        ),
        ranked AS (
            SELECT
                iso3_code, country_name, region, continent, market_year,
                domestic_consumption, per_capita_kg_per_person,
                consumption_cagr_5y, population, import_dependency_ratio,
                PERCENT_RANK() OVER (ORDER BY domestic_consumption) AS size_score,
                PERCENT_RANK() OVER (ORDER BY COALESCE(consumption_cagr_5y, -1)) AS growth_score,
                PERCENT_RANK() OVER (ORDER BY population) AS population_score,
                PERCENT_RANK() OVER (ORDER BY COALESCE(import_dependency_ratio, 0)) AS import_openness_score
            FROM base
        )
        SELECT *,
            ({w_size} * size_score + {w_growth} * growth_score + {w_pop} * population_score + {w_import} * import_openness_score) AS composite_score
        FROM ranked
        ORDER BY composite_score DESC
        LIMIT 20
        """
        top_markets = run_query(score_query)

        if len(top_markets) >= 3:
            top3 = top_markets.head(3)
            cols = st.columns(3)
            for idx, (col, (_, row)) in enumerate(zip(cols, top3.iterrows())):
                with col:
                    st.metric(
                        label=f"#{idx + 1}: {row['country_name']}",
                        value=f"Score: {row['composite_score']:.2f}",
                    )
                    st.caption(f"**Region:** {row['region']}")
                    st.caption(f"**Population:** {pop_label(row['population'])}")
                    st.caption(f"**Consumption:** {num_label(row['domestic_consumption'])} (1000 60kg bags)")
                    if pd.notna(row["consumption_cagr_5y"]):
                        st.caption(f"**5Y CAGR:** {row['consumption_cagr_5y'] * 100:.1f}%")
                    if pd.notna(row["import_dependency_ratio"]):
                        st.caption(f"**Import dependency:** {row['import_dependency_ratio'] * 100:.0f}%")
                    st.markdown(f"<div class='insight-card'>{narrative_for_country(row, idx + 1)}</div>", unsafe_allow_html=True)

            st.markdown("---")
            st.subheader("Why these three?")
            st.markdown(
                """
                The composite score weighs four factors: **market size** (current consumption), **growth** (5-year CAGR), **population** (long-term demand potential), and **import openness** (low local production means more room for an import-led chain).

                The top three balance scale and trajectory:
                - **#1 captures scale + growth**: the must-have market
                - **#2 captures emerging high-growth**: the bet on tomorrow's consumer
                - **#3 captures growth from a coffee-aware base**: established palate, rising demand, but strategic caveats may matter

                Use the sidebar weights to stress-test this ranking against your own strategic priorities.
                """
            )

            commentary_map = {
                "China": "Massive demand runway plus proven chain economics from local challengers makes this the anchor recommendation.",
                "Egypt": "Unexpected but analytically strong: scale, import dependency, and urban cafe adoption create whitespace for a branded entrant.",
                "Viet Nam": "Demand is rising from a coffee-native culture, though ACME would need a sharper competitive strategy against entrenched local brands.",
            }
            st.subheader("Strategic commentary")
            for _, row in top3.iterrows():
                note = commentary_map.get(row["country_name"], "Strong analytical candidate; strategic overlay should focus on fit, competition, and operating model.")
                st.markdown(f"<div class='insight-card'><strong>{row['country_name']}:</strong> {note}</div>", unsafe_allow_html=True)

            st.markdown("---")
            st.subheader("Full top 20 ranking")
            display_cols = [
                "country_name",
                "region",
                "domestic_consumption",
                "consumption_cagr_5y",
                "population",
                "import_dependency_ratio",
                "composite_score",
            ]
            display_df = top_markets[display_cols].copy()
            display_df.columns = [
                "Country",
                "Region",
                "Consumption (1000 bags)",
                "5Y CAGR",
                "Population",
                "Import Dependency",
                "Composite Score",
            ]
            display_df["5Y CAGR"] = display_df["5Y CAGR"].apply(pct_label)
            display_df["Import Dependency"] = display_df["Import Dependency"].apply(lambda x: f"{x * 100:.0f}%" if pd.notna(x) else "N/A")
            display_df["Population"] = display_df["Population"].apply(pop_label)
            display_df["Consumption (1000 bags)"] = display_df["Consumption (1000 bags)"].apply(lambda x: num_label(x))
            display_df["Composite Score"] = display_df["Composite Score"].apply(lambda x: f"{x:.3f}")
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.warning("Not enough data for current filter selection.")

with tab2:
    st.header("Is this a good time to enter the coffee market?")

    global_trends = run_query("SELECT * FROM analytics.v_global_trends ORDER BY market_year")
    global_trends_filtered = global_trends[
        (global_trends["market_year"] >= selected_year_range[0]) & (global_trends["market_year"] <= selected_year_range[1])
    ]

    if len(global_trends_filtered) >= 2:
        latest = global_trends_filtered.iloc[-1]
        prior = global_trends_filtered.iloc[0]
        years_span = latest["market_year"] - prior["market_year"]
        if years_span > 0 and prior["total_consumption"] > 0:
            growth_pct = ((latest["total_consumption"] / prior["total_consumption"]) ** (1 / years_span) - 1) * 100
        else:
            growth_pct = 0

        col1, col2, col3 = st.columns(3)
        col1.metric("Latest global consumption", f"{latest['total_consumption'] / 1000:.1f}M bags")
        col2.metric(f"CAGR ({int(prior['market_year'])} to {int(latest['market_year'])})", f"{growth_pct:.2f}%")
        col3.metric("Reporting countries", f"{int(latest['reporting_countries'])}")

    fig_trend = go.Figure()
    fig_trend.add_trace(
        go.Scatter(
            x=global_trends_filtered["market_year"],
            y=global_trends_filtered["total_consumption"] / 1000,
            name="Consumption",
            mode="lines+markers",
            line=dict(width=3, color="#c9822b"),
        )
    )
    fig_trend.add_trace(
        go.Scatter(
            x=global_trends_filtered["market_year"],
            y=global_trends_filtered["total_production"] / 1000,
            name="Production",
            mode="lines+markers",
            line=dict(width=3, dash="dash", color="#2f5d50"),
        )
    )
    fig_trend.update_layout(
        title="Global Coffee Consumption vs Production (Million 60kg Bags)",
        xaxis_title="Year",
        yaxis_title="Million 60kg Bags",
        hovermode="x unified",
        height=450,
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    st.markdown(
        """
        **Read:** Coffee demand has grown steadily and consistently outpaces supply expansion. The widening gap between consumption and production is structural and it signals a market that can absorb new chains without relying only on share capture.
        """
    )

    st.subheader("Regional consumption distribution")
    regional_year = selected_year_range[1]
    regional_query = f"""
    SELECT region, SUM(domestic_consumption) AS total_consumption, COUNT(DISTINCT iso3_code) AS countries
    FROM analytics.v_country_year_metrics
    WHERE region IS NOT NULL
      AND market_year = {regional_year}
      AND domestic_consumption IS NOT NULL
    GROUP BY region
    ORDER BY total_consumption DESC
    """
    regional = run_query(regional_query)

    fig_regional = px.bar(
        regional,
        x="region",
        y="total_consumption",
        title=f"Consumption by Region ({regional_year})",
        labels={"total_consumption": "Consumption (1000 60kg bags)", "region": "Region"},
        color="total_consumption",
        color_continuous_scale=["#c7dfd8", "#2f5d50"],
    )
    fig_regional.update_layout(height=400, coloraxis_showscale=False)
    st.plotly_chart(fig_regional, use_container_width=True)

with tab3:
    st.header("Market Comparison: Where the Opportunity Lives")

    if not selected_regions:
        st.warning("Select at least one region to compare markets.")
    else:
        snapshot = run_query(
            """
            SELECT * FROM analytics.v_latest_year_snapshot
            WHERE domestic_consumption IS NOT NULL
              AND population IS NOT NULL
              AND consumption_cagr_5y IS NOT NULL
            """
        )
        snapshot = snapshot[snapshot["region"].isin(selected_regions)]

        fig_scatter = px.scatter(
            snapshot,
            x="domestic_consumption",
            y="consumption_cagr_5y",
            size="population",
            color="region",
            hover_name="country_name",
            log_x=True,
            title="Growth (5Y CAGR) vs Market Size - bubble size = population",
            labels={
                "domestic_consumption": "Current consumption (log scale, 1000 bags)",
                "consumption_cagr_5y": "5-year CAGR",
            },
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_scatter.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        fig_scatter.update_layout(height=550)
        st.plotly_chart(fig_scatter, use_container_width=True)

        st.markdown(
            """
            **Read the quadrants:**
            - **Top-right:** large + growing = priority markets
            - **Top-left:** small + growing = early-stage opportunity, high upside
            - **Bottom-right:** large + stagnant = tougher entry, more mature competition
            - **Bottom-left:** small + stagnant = lower strategic priority
            """
        )

        st.subheader("Per-capita consumption by country")
        fig_map = px.choropleth(
            snapshot,
            locations="iso3_code",
            color="per_capita_kg_per_person",
            hover_name="country_name",
            color_continuous_scale="Tealgrn",
            title="Per-capita coffee consumption (kg per person per year)",
            labels={"per_capita_kg_per_person": "Kg per person per year"},
        )
        fig_map.update_layout(height=500)
        st.plotly_chart(fig_map, use_container_width=True)

with tab4:
    st.header("Country Deep Dive")

    countries = run_query("SELECT DISTINCT iso3_code, country_name FROM analytics.v_latest_year_snapshot ORDER BY country_name")
    country_options = countries.set_index("iso3_code")["country_name"].to_dict()
    selected_iso = st.selectbox("Select country", options=list(country_options.keys()), format_func=lambda x: country_options[x])

    country_history = run_query(
        f"""
        SELECT * FROM analytics.v_country_year_metrics
        WHERE iso3_code = '{selected_iso}'
        ORDER BY market_year
        """
    )

    if len(country_history) > 0:
        # Pick the most recent year that has a non-null population for headline metrics.
        # USDA market_year extends to 2025 (forecast) but World Bank population stops at 2024,
        # so the most recent fact_coffee row has no population match. Use the most recent
        # row with population for the headline; the time series chart still uses all years.
        pop_rows = country_history[country_history["population"].notna()]
        if len(pop_rows) > 0:
            latest = pop_rows.iloc[-1]
        else:
            latest = country_history.iloc[-1]

        st.caption(f"Headline metrics shown for {int(latest['market_year'])} (most recent year with population data). Time-series chart below extends through {int(country_history['market_year'].max())}.")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Latest consumption", num_label(latest["domestic_consumption"]))
        col2.metric("Production", num_label(latest["production"]))
        col3.metric("Population", pop_label(latest["population"]))
        col4.metric("Per-capita", num_label(latest["per_capita_kg_per_person"], 2))

        fig_country = go.Figure()
        fig_country.add_trace(go.Scatter(x=country_history["market_year"], y=country_history["domestic_consumption"], name="Consumption", mode="lines+markers"))
        fig_country.add_trace(go.Scatter(x=country_history["market_year"], y=country_history["production"], name="Production", mode="lines+markers"))
        fig_country.add_trace(go.Scatter(x=country_history["market_year"], y=country_history["bean_imports"], name="Imports", mode="lines+markers"))
        fig_country.update_layout(
            title=f"{country_options[selected_iso]} - Coffee metrics over time",
            xaxis_title="Year",
            yaxis_title="1000 60kg bags",
            hovermode="x unified",
            height=500,
        )
        st.plotly_chart(fig_country, use_container_width=True)

        latest_snapshot = run_query(
            f"SELECT * FROM analytics.v_latest_year_snapshot WHERE iso3_code = '{selected_iso}'"
        )
        if not latest_snapshot.empty:
            row = latest_snapshot.iloc[0]
            region_label = row["region"] if pd.notna(row["region"]) else "N/A"
            st.markdown(
                f"""
                <div class='insight-card'>
                    <strong>Opportunity lens:</strong> {row['country_name']} sits in <strong>{region_label}</strong> with current consumption of <strong>{num_label(row['domestic_consumption'])}</strong> and import dependency of <strong>{pct_label(row['import_dependency_ratio'])}</strong>. This helps frame whether ACME is entering a locally supplied market or an import-led one.
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.warning("No data for selected country.")

with tab5:
    st.header("Methodology")

    st.markdown(
        """
        ### Data sources
        - **USDA PSD Coffee** - country-level production, consumption, imports, exports, and stocks
        - **World Bank Population** - total population by country and year
        - **opendatasoft Country Codes** - ISO mapping bridge for joins

        ### Pipeline
        1. Raw CSVs loaded to `raw` schema in PostgreSQL
        2. Country name reconciliation via manual override dictionary + case-insensitive matching to ISO3
        3. Coffee data pivoted from long to wide format in `analytics.fact_coffee`
        4. Per-capita and growth metrics derived in views
        5. Composite scoring via four percentile-ranked dimensions

        ### Composite scoring formula
        `composite = 0.35 x size + 0.30 x growth + 0.20 x population + 0.15 x import_openness`

        Each component is a percentile rank (0 to 1) across all countries with valid data.

        Use the sidebar sliders to stress-test the weights against your own priorities.

        ### Assumptions
        - USDA market year is approximated as calendar year for the population join
        - Countries with no recent consumption data are excluded from ranking
        - Regional and continental classifications come from the country codes bridge table
        - North Macedonia was not mapped in USDA data and remains immaterial to the ranking output

        ### Known gaps
        - No disposable income, urbanization, or cafe density measures
        - No direct competitive landscape or chain footprint data
        - No logistics-cost or supply-chain feasibility variables
        - Per-capita conversion is a demand-intensity proxy built from USDA bag units and population
        """
    )
