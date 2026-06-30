from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

MANUAL_OVERRIDES = {
    "Korea, South": "KOR", "Korea, North": "PRK", "Burma": "MMR",
    "Congo (Kinshasa)": "COD", "Congo (Brazzaville)": "COG",
    "Cote d'Ivoire": "CIV", "C??te d'Ivoire": "CIV", "Russia": "RUS",
    "Vietnam": "VNM", "Venezuela": "VEN", "Yemen (Sanaa)": "YEM",
    "Iran": "IRN", "Tanzania": "TZA", "Macedonia": "MKD",
    "Cape Verde": "CPV", "Slovak Republic": "SVK", "Laos": "LAO",
    "Brunei": "BRN", "Bolivia": "BOL", "Czech Republic": "CZE",
    "Egypt": "EGY", "Hong Kong": "HKG", "Macau": "MAC", "Moldova": "MDA",
    "Syria": "SYR", "Taiwan": "TWN", "United Kingdom": "GBR",
    "United States": "USA", "Gambia, The": "GMB", "Bahamas, The": "BHS",
}

AGGREGATES_TO_EXCLUDE = {
    "European Union", "European Union-27", "European Union-28",
    "Former Czechoslovakia", "Former Yugoslavia", "Former USSR",
    "Other", "Unknown",
}

ENGLISH_NAME_CANDIDATES = [
    "LABEL EN",
    "Label en",
    "English Name",
    "english_name",
    "name",
]
ISO3_CANDIDATES = ["ISO3 CODE", "ISO3", "iso3_code"]


def choose_column(columns: list[str], candidates: list[str], label: str) -> str:
    print(f"Available columns for {label}: {columns}")
    for candidate in candidates:
        if candidate in columns:
            print(f"Selected {label} column: {candidate}")
            return candidate
    raise KeyError(f"Could not identify {label} column from: {columns}")


def build_country_mapping(coffee_countries, country_codes_df: pd.DataFrame) -> pd.DataFrame:
    columns = country_codes_df.columns.tolist()
    english_name_col = choose_column(columns, ENGLISH_NAME_CANDIDATES, "English name")
    iso3_col = choose_column(columns, ISO3_CANDIDATES, "ISO3")

    exact_lookup = {}
    for _, row in country_codes_df[[english_name_col, iso3_col]].dropna().iterrows():
        exact_lookup[str(row[english_name_col]).strip().lower()] = str(row[iso3_col]).strip()

    records = []
    for country in sorted(pd.Series(coffee_countries).dropna().astype(str).unique().tolist()):
        if country in AGGREGATES_TO_EXCLUDE:
            records.append(
                {
                    "coffee_country_name": country,
                    "iso3_code": None,
                    "match_method": "excluded",
                }
            )
        elif country in MANUAL_OVERRIDES:
            records.append(
                {
                    "coffee_country_name": country,
                    "iso3_code": MANUAL_OVERRIDES[country],
                    "match_method": "manual_override",
                }
            )
        else:
            iso3_code = exact_lookup.get(country.strip().lower())
            if iso3_code:
                records.append(
                    {
                        "coffee_country_name": country,
                        "iso3_code": iso3_code,
                        "match_method": "exact_match",
                    }
                )
            else:
                records.append(
                    {
                        "coffee_country_name": country,
                        "iso3_code": None,
                        "match_method": "unmapped",
                    }
                )

    return pd.DataFrame(records)


def run_verification() -> pd.DataFrame:
    coffee_df = pd.read_csv(RAW_DIR / "psd_coffee.csv")
    country_codes_df = pd.read_csv(RAW_DIR / "country_codes.csv", sep=";")
    coffee_countries = sorted(coffee_df["Country_Name"].dropna().unique().tolist())

    mapping_df = build_country_mapping(coffee_countries, country_codes_df)

    total_countries = len(mapping_df)
    manual_override_count = int((mapping_df["match_method"] == "manual_override").sum())
    exact_match_count = int((mapping_df["match_method"] == "exact_match").sum())
    unmapped_count = int((mapping_df["match_method"] == "unmapped").sum())
    excluded_count = int((mapping_df["match_method"] == "excluded").sum())
    mapped_count = manual_override_count + exact_match_count

    print(f"total countries: {total_countries}")
    print(f"manual_override count: {manual_override_count}")
    print(f"exact_match count: {exact_match_count}")
    print(f"unmapped count: {unmapped_count}")
    print(f"excluded count: {excluded_count}")

    unmapped_countries = mapping_df.loc[mapping_df["match_method"] == "unmapped", "coffee_country_name"].tolist()
    if unmapped_countries:
        for country in unmapped_countries:
            print(f"REVIEW REQUIRED: {country}")

    assert mapped_count >= 70, f"Mapped country count too low: {mapped_count}"
    assert unmapped_count <= 15, f"Too many unmapped countries: {unmapped_count}"

    print("STEP 1 VERIFICATION PASSED")
    return mapping_df


if __name__ == "__main__":
    run_verification()
