from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "attribute_discovery.txt"


def load_engine():
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(database_url)


def choose_exact_attribute(attributes: list[str], category: str) -> str:
    preferred = {
        "consumption": ["Domestic Consumption"],
        "production": ["Production"],
        "imports": ["Bean Imports", "Imports"],
        "exports": ["Bean Exports", "Exports"],
    }
    for candidate in preferred[category]:
        if candidate in attributes:
            return candidate
    raise AssertionError(f"Could not select exact attribute for {category} from {attributes}")


def run_discovery(output_path: Path = OUTPUT_PATH) -> dict[str, object]:
    engine = load_engine()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    queries = {
        "attribute_counts": "SELECT attribute_description, COUNT(*) AS rows FROM raw.coffee GROUP BY attribute_description ORDER BY rows DESC, attribute_description",
        "year_range": "SELECT MIN(market_year) AS min_yr, MAX(market_year) AS max_yr, COUNT(DISTINCT market_year) AS n_years FROM raw.coffee",
        "attribute_country_counts": "SELECT attribute_description, COUNT(DISTINCT iso3_code) AS n_countries FROM raw.coffee GROUP BY attribute_description ORDER BY n_countries DESC, attribute_description",
        "top_countries": "SELECT iso3_code, COUNT(*) AS rows FROM raw.coffee GROUP BY iso3_code ORDER BY rows DESC, iso3_code LIMIT 10",
        "unit_samples": "SELECT DISTINCT attribute_description, unit_description FROM raw.coffee ORDER BY attribute_description, unit_description",
    }

    with engine.connect() as conn:
        attribute_counts = pd.read_sql(text(queries["attribute_counts"]), conn)
        year_range = pd.read_sql(text(queries["year_range"]), conn)
        attribute_country_counts = pd.read_sql(text(queries["attribute_country_counts"]), conn)
        top_countries = pd.read_sql(text(queries["top_countries"]), conn)
        unit_samples = pd.read_sql(text(queries["unit_samples"]), conn)

    attributes = attribute_counts["attribute_description"].astype(str).tolist()
    consumption_matches = [attr for attr in attributes if "consumption" in attr.lower()]
    production_matches = [attr for attr in attributes if "production" in attr.lower()]
    imports_matches = [attr for attr in attributes if "imports" in attr.lower()]
    exports_matches = [attr for attr in attributes if "exports" in attr.lower()]

    assert consumption_matches, "No attribute_description matched Consumption"
    assert production_matches, "No attribute_description matched Production"
    assert imports_matches, "No attribute_description matched Imports"
    assert exports_matches, "No attribute_description matched Exports"

    selected_attributes = {
        "consumption": choose_exact_attribute(consumption_matches, "consumption"),
        "production": choose_exact_attribute(production_matches, "production"),
        "imports": choose_exact_attribute(imports_matches, "imports"),
        "exports": choose_exact_attribute(exports_matches, "exports"),
    }

    lines = []
    lines.append("=== 1.1 Attribute Counts ===")
    lines.append(attribute_counts.to_string(index=False))
    lines.append("")
    lines.append("=== 1.2 Market Year Range ===")
    lines.append(year_range.to_string(index=False))
    lines.append("")
    lines.append("=== 1.3 Distinct ISO3 Counts Per Attribute ===")
    lines.append(attribute_country_counts.to_string(index=False))
    lines.append("")
    lines.append("=== 1.4 Top 10 Countries By Row Count ===")
    lines.append(top_countries.to_string(index=False))
    lines.append("")
    lines.append("=== 1.5 Unit Description Samples ===")
    lines.append(unit_samples.to_string(index=False))
    lines.append("")
    lines.append("=== Verification Matches ===")
    lines.append(f"Consumption matches: {consumption_matches}")
    lines.append(f"Production matches: {production_matches}")
    lines.append(f"Imports matches: {imports_matches}")
    lines.append(f"Exports matches: {exports_matches}")
    lines.append(f"Selected consumption attribute: {selected_attributes['consumption']}")
    lines.append(f"Selected production attribute: {selected_attributes['production']}")
    lines.append(f"Selected imports attribute: {selected_attributes['imports']}")
    lines.append(f"Selected exports attribute: {selected_attributes['exports']}")
    lines.append("STEP 1 VERIFICATION PASSED")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(attribute_counts.to_string(index=False))
    print(year_range.to_string(index=False))
    print(attribute_country_counts.to_string(index=False))
    print(top_countries.to_string(index=False))
    print(unit_samples.to_string(index=False))
    print(f"Consumption matches: {consumption_matches}")
    print(f"Production matches: {production_matches}")
    print(f"Imports matches: {imports_matches}")
    print(f"Exports matches: {exports_matches}")
    print(f"Consumption attr name: {selected_attributes['consumption']}")
    print(f"Production attr name: {selected_attributes['production']}")
    print(f"Imports attr name: {selected_attributes['imports']}")
    print(f"Exports attr name: {selected_attributes['exports']}")
    print("STEP 1 VERIFICATION PASSED")

    return {
        "selected_attributes": selected_attributes,
        "year_range": {
            "min": int(year_range.loc[0, "min_yr"]),
            "max": int(year_range.loc[0, "max_yr"]),
            "n_years": int(year_range.loc[0, "n_years"]),
        },
    }


if __name__ == "__main__":
    run_discovery()
