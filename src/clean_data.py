from __future__ import annotations

from pathlib import Path

import pandas as pd

from country_mapping import build_country_mapping, choose_column, ENGLISH_NAME_CANDIDATES, ISO3_CANDIDATES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def clean_coffee_data() -> pd.DataFrame:
    coffee_df = pd.read_csv(RAW_DIR / "psd_coffee.csv")
    country_codes_df = pd.read_csv(RAW_DIR / "country_codes.csv", sep=";")

    mapping_df = build_country_mapping(coffee_df["Country_Name"].dropna().unique().tolist(), country_codes_df)
    valid_mapping = mapping_df.loc[mapping_df["match_method"].isin(["manual_override", "exact_match"]), ["coffee_country_name", "iso3_code"]]

    merged = coffee_df.merge(valid_mapping, left_on="Country_Name", right_on="coffee_country_name", how="left")
    cleaned = merged.loc[:, [
        "iso3_code",
        "Country_Name",
        "Market_Year",
        "Attribute_ID",
        "Attribute_Description",
        "Value",
        "Unit_Description",
    ]].rename(columns={
        "Country_Name": "country_name",
        "Market_Year": "market_year",
        "Attribute_ID": "attribute_id",
        "Attribute_Description": "attribute_description",
        "Value": "value",
        "Unit_Description": "unit_description",
    })

    cleaned["market_year"] = pd.to_numeric(cleaned["market_year"], errors="coerce").astype("Int64")
    cleaned["attribute_id"] = pd.to_numeric(cleaned["attribute_id"], errors="coerce").astype("Int64")
    cleaned["value"] = pd.to_numeric(cleaned["value"], errors="coerce")

    cleaned = cleaned.dropna(subset=["iso3_code", "value", "market_year", "attribute_id"]).copy()
    cleaned["market_year"] = cleaned["market_year"].astype(int)
    cleaned["attribute_id"] = cleaned["attribute_id"].astype(int)

    output_path = PROCESSED_DIR / "coffee_clean.csv"
    cleaned.to_csv(output_path, index=False)
    return cleaned


def clean_population_data(valid_iso3_codes: set[str]) -> pd.DataFrame:
    population_df = pd.read_csv(RAW_DIR / "world_population.csv", skiprows=4)
    year_columns = [column for column in population_df.columns if str(column).isdigit()]

    long_df = population_df.melt(
        id_vars=["Country Name", "Country Code"],
        value_vars=year_columns,
        var_name="year",
        value_name="population",
    ).rename(columns={
        "Country Name": "country_name",
        "Country Code": "iso3_code",
    })

    long_df["year"] = pd.to_numeric(long_df["year"], errors="coerce").astype("Int64")
    long_df["population"] = pd.to_numeric(long_df["population"], errors="coerce")
    long_df = long_df.dropna(subset=["year", "population", "iso3_code"]).copy()
    long_df["year"] = long_df["year"].astype(int)
    long_df = long_df.loc[long_df["iso3_code"].isin(valid_iso3_codes)].copy()

    output_path = PROCESSED_DIR / "population_clean.csv"
    long_df.to_csv(output_path, index=False)
    return long_df


def clean_country_codes() -> pd.DataFrame:
    country_codes_df = pd.read_csv(RAW_DIR / "country_codes.csv", sep=";")
    columns = country_codes_df.columns.tolist()
    print(f"country_codes raw columns: {columns}")

    english_name_col = choose_column(columns, ENGLISH_NAME_CANDIDATES, "English name")
    iso3_col = choose_column(columns, ISO3_CANDIDATES, "ISO3")
    iso2_col = choose_column(columns, ["ISO2 CODE", "ISO2", "iso2_code"], "ISO2")

    cleaned = pd.DataFrame(
        {
            "iso3_code": country_codes_df[iso3_col].astype(str).str.strip(),
            "iso2_code": country_codes_df[iso2_col].astype(str).str.strip(),
            "english_name": country_codes_df[english_name_col].astype(str).str.strip(),
            "region": "",
            "sub_region": "",
            "continent": "",
        }
    )
    cleaned = cleaned.replace({"nan": pd.NA, "None": pd.NA})
    cleaned = cleaned.dropna(subset=["iso3_code"]).copy()

    output_path = PROCESSED_DIR / "country_codes_clean.csv"
    cleaned.to_csv(output_path, index=False)
    return cleaned


def run_verification() -> dict[str, int]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    country_codes_clean = clean_country_codes()
    valid_iso3_codes = set(country_codes_clean["iso3_code"].dropna().astype(str))
    coffee_clean = clean_coffee_data()
    population_clean = clean_population_data(valid_iso3_codes)

    coffee_row_count = len(coffee_clean)
    coffee_unique_iso3_count = coffee_clean["iso3_code"].nunique()
    coffee_year_range = (int(coffee_clean["market_year"].min()), int(coffee_clean["market_year"].max()))
    coffee_null_value_count = int(coffee_clean["value"].isna().sum())

    population_row_count = len(population_clean)
    population_unique_iso3_count = population_clean["iso3_code"].nunique()
    population_year_range = (int(population_clean["year"].min()), int(population_clean["year"].max()))
    population_null_count = int(population_clean["population"].isna().sum())

    country_codes_row_count = len(country_codes_clean)
    country_codes_null_iso3_count = int(country_codes_clean["iso3_code"].isna().sum())

    print(f"coffee_clean: row_count={coffee_row_count}, unique_iso3_count={coffee_unique_iso3_count}, year_range={coffee_year_range}, null_value_count={coffee_null_value_count}")
    print(f"population_clean: row_count={population_row_count}, unique_iso3_count={population_unique_iso3_count}, year_range={population_year_range}, null_population_count={population_null_count}")
    print(f"country_codes_clean: row_count={country_codes_row_count}, null_iso3_count={country_codes_null_iso3_count}")

    coffee_missing_iso3 = set(coffee_clean["iso3_code"]) - set(country_codes_clean["iso3_code"])
    population_missing_iso3 = set(population_clean["iso3_code"]) - set(country_codes_clean["iso3_code"])
    print(f"coffee iso3 missing from country_codes_clean: {sorted(coffee_missing_iso3)}")
    print(f"population iso3 missing from country_codes_clean: {sorted(population_missing_iso3)}")

    assert coffee_row_count > 50000, f"coffee_clean row_count too low: {coffee_row_count}"
    assert coffee_unique_iso3_count >= 70, f"coffee unique_iso3_count too low: {coffee_unique_iso3_count}"
    assert coffee_null_value_count == 0, f"coffee null_value_count not zero: {coffee_null_value_count}"
    assert coffee_year_range[0] >= 1960 and coffee_year_range[1] >= 2020, f"coffee year range unexpected: {coffee_year_range}"

    assert population_row_count > 10000, f"population_clean row_count too low: {population_row_count}"
    assert population_unique_iso3_count >= 200, f"population unique_iso3_count too low: {population_unique_iso3_count}"
    assert population_null_count == 0, f"population null_population_count not zero: {population_null_count}"
    assert population_year_range[0] >= 1960 and population_year_range[1] >= 2020, f"population year range unexpected: {population_year_range}"

    assert country_codes_row_count >= 200, f"country_codes_clean row_count too low: {country_codes_row_count}"
    assert country_codes_null_iso3_count == 0, f"country_codes_clean null iso3 count not zero: {country_codes_null_iso3_count}"
    assert len(coffee_missing_iso3) == 0, f"coffee iso3 not found in country_codes_clean: {sorted(coffee_missing_iso3)}"
    assert len(population_missing_iso3) == 0, f"population iso3 not found in country_codes_clean: {sorted(population_missing_iso3)}"

    print("STEP 2 VERIFICATION PASSED")
    return {
        "coffee_clean_rows": coffee_row_count,
        "population_clean_rows": population_row_count,
        "country_codes_clean_rows": country_codes_row_count,
    }


if __name__ == "__main__":
    run_verification()
