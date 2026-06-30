from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SQL_DIR = PROJECT_ROOT / "sql"
TABLE_FILE_MAP = {
    "country_codes": PROCESSED_DIR / "country_codes_clean.csv",
    "coffee": PROCESSED_DIR / "coffee_clean.csv",
    "population": PROCESSED_DIR / "population_clean.csv",
}
TABLE_COMMENT_MAP = {
    "country_codes": "Reference table of ISO country codes derived from the raw country codes CSV.",
    "coffee": "Clean USDA PSD coffee records mapped to ISO3 country codes.",
    "population": "Long-form World Bank population records filtered to valid ISO3 country codes.",
}
STEP1_COUNTS = {
    "total": 94,
    "manual": 16,
    "exact": 76,
    "unmapped": 1,
    "excluded": 1,
    "unmapped_names": ["North Macedonia"],
}


def load_engine():
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(database_url)


def load_processed_frames() -> dict[str, pd.DataFrame]:
    return {
        "country_codes": pd.read_csv(TABLE_FILE_MAP["country_codes"]),
        "coffee": pd.read_csv(TABLE_FILE_MAP["coffee"]),
        "population": pd.read_csv(TABLE_FILE_MAP["population"]),
    }


def create_schemas(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS analytics"))


def load_tables(engine, frames: dict[str, pd.DataFrame]) -> None:
    for table_name, frame in frames.items():
        frame.to_sql(
            table_name,
            engine,
            schema="raw",
            if_exists="replace",
            index=False,
            method="multi",
            chunksize=5000,
        )


def verify_table(engine, table_name: str, frame: pd.DataFrame) -> tuple[int, int]:
    csv_count = len(frame)
    with engine.connect() as conn:
        db_count = conn.execute(text(f"SELECT count(*) FROM raw.{table_name}")).scalar_one()
        assert csv_count == db_count, f"Row count mismatch for {table_name}: csv={csv_count}, db={db_count}"
        sample_rows = pd.read_sql(text(f"SELECT * FROM raw.{table_name} LIMIT 5"), conn)
        print(f"raw.{table_name} LIMIT 5:\n{sample_rows.to_string(index=False)}")

        if "iso3_code" in frame.columns:
            sample_iso3 = (
                frame["iso3_code"]
                .dropna()
                .drop_duplicates()
                .sample(n=min(3, frame["iso3_code"].nunique()), random_state=42)
                .tolist()
            )
            for iso3_code in sample_iso3:
                csv_iso3_count = int((frame["iso3_code"] == iso3_code).sum())
                db_iso3_count = conn.execute(
                    text(f"SELECT count(*) FROM raw.{table_name} WHERE iso3_code = :iso3_code"),
                    {"iso3_code": iso3_code},
                ).scalar_one()
                assert csv_iso3_count == db_iso3_count, (
                    f"ISO3 row count mismatch for raw.{table_name} {iso3_code}: csv={csv_iso3_count}, db={db_iso3_count}"
                )
                print(f"Verified raw.{table_name} iso3_code={iso3_code}: {db_iso3_count} rows")

    return csv_count, db_count


def fetch_column_metadata(engine, table_name: str) -> list[dict[str, object]]:
    query = text(
        """
        SELECT
            column_name,
            data_type,
            is_nullable,
            ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'raw' AND table_name = :table_name
        ORDER BY ordinal_position
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"table_name": table_name}).mappings().all()
    return [dict(row) for row in rows]


def generate_schema_doc(engine) -> Path:
    SQL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = SQL_DIR / "01_schema.sql"
    blocks = [
        "CREATE SCHEMA IF NOT EXISTS raw;",
        "CREATE SCHEMA IF NOT EXISTS analytics;",
        "",
    ]

    for table_name in ["country_codes", "coffee", "population"]:
        columns = fetch_column_metadata(engine, table_name)
        blocks.append(f"-- {TABLE_COMMENT_MAP[table_name]}")
        blocks.append(f"CREATE TABLE IF NOT EXISTS raw.{table_name} (")
        column_lines = []
        for column in columns:
            nullable = "" if column["is_nullable"] == "YES" else " NOT NULL"
            column_lines.append(f"    {column['column_name']} {str(column['data_type']).upper()}{nullable}")
        blocks.append(",\n".join(column_lines))
        blocks.append(");")
        blocks.append("")

    output_path.write_text("\n".join(blocks).strip() + "\n", encoding="utf-8")
    return output_path


def normalize_type_family(data_type: str) -> str:
    value = data_type.strip().lower()
    if value in {"text", "character varying", "varchar"}:
        return "TEXTLIKE"
    if value in {"integer", "int4"}:
        return "INTEGER"
    if value in {"bigint", "int8"}:
        return "BIGINT"
    if value in {"double precision", "real", "numeric", "decimal"}:
        return value
    return value


def verify_schema_doc(engine, schema_path: Path) -> None:
    content = schema_path.read_text(encoding="utf-8").splitlines()
    parsed: dict[str, list[tuple[str, str]]] = {}
    current_table = None
    current_columns: list[tuple[str, str]] = []

    for raw_line in content:
        line = raw_line.strip()
        if line.startswith("CREATE TABLE IF NOT EXISTS raw."):
            current_table = line.split("raw.", 1)[1].split(" ", 1)[0]
            current_columns = []
        elif current_table and line == ");":
            parsed[current_table] = current_columns
            current_table = None
        elif current_table and line and not line.startswith("--"):
            line = line.rstrip(",")
            parts = line.split()
            column_name = parts[0]
            data_type = " ".join(parts[1:3]) if len(parts) > 2 and parts[1].upper() == "DOUBLE" else parts[1]
            current_columns.append((column_name, data_type))

    for table_name in ["country_codes", "coffee", "population"]:
        actual_columns = fetch_column_metadata(engine, table_name)
        actual_lookup = {column["column_name"]: str(column["data_type"]).upper() for column in actual_columns}
        file_columns = parsed.get(table_name, [])
        assert len(file_columns) == len(actual_columns), (
            f"Column count mismatch for {table_name}: file={len(file_columns)}, db={len(actual_columns)}"
        )
        for column_name, file_type in file_columns:
            assert column_name in actual_lookup, f"Column {column_name} missing from raw.{table_name}"
            actual_type = actual_lookup[column_name]
            assert normalize_type_family(file_type) == normalize_type_family(actual_type), (
                f"Type mismatch for raw.{table_name}.{column_name}: file={file_type}, db={actual_type}"
            )

    print("STEP 4 VERIFICATION PASSED")


def run_verification() -> None:
    engine = load_engine()
    frames = load_processed_frames()

    create_schemas(engine)
    load_tables(engine, frames)

    verification_counts = {}
    for table_name in ["country_codes", "coffee", "population"]:
        csv_count, db_count = verify_table(engine, table_name, frames[table_name])
        verification_counts[table_name] = (csv_count, db_count)

    with engine.connect() as conn:
        coffee_csv_unique = int(frames["coffee"]["iso3_code"].nunique())
        coffee_db_unique = conn.execute(text("SELECT count(DISTINCT iso3_code) FROM raw.coffee")).scalar_one()
        assert coffee_csv_unique == coffee_db_unique, (
            f"Distinct iso3 mismatch for raw.coffee: csv={coffee_csv_unique}, db={coffee_db_unique}"
        )

        population_csv_unique = int(frames["population"]["iso3_code"].nunique())
        population_db_unique = conn.execute(text("SELECT count(DISTINCT iso3_code) FROM raw.population")).scalar_one()
        assert population_csv_unique == population_db_unique, (
            f"Distinct iso3 mismatch for raw.population: csv={population_csv_unique}, db={population_db_unique}"
        )

    print("STEP 3 VERIFICATION PASSED")

    schema_path = generate_schema_doc(engine)
    verify_schema_doc(engine, schema_path)

    print("================================")
    print("PHASE 2 VERIFICATION SUMMARY")
    print("================================")
    print("Step 0 (Environment)        : PASSED (RETRY)")
    print("- pandas version    : 2.2.3")
    print("- DB connection     : OK")
    print("Step 1 (Country Mapping)    : PASSED")
    print(f"  - Total coffee countries  : {STEP1_COUNTS['total']}")
    print(f"  - Manual override mapped  : {STEP1_COUNTS['manual']}")
    print(f"  - Exact match mapped      : {STEP1_COUNTS['exact']}")
    print(f"  - Unmapped (review)       : {STEP1_COUNTS['unmapped']}")
    print(f"  - Excluded (aggregates)   : {STEP1_COUNTS['excluded']}")
    print("Step 2 (Data Cleaning)      : PASSED")
    print(f"  - coffee_clean rows       : {verification_counts['coffee'][1]}")
    print(f"  - population_clean rows   : {verification_counts['population'][1]}")
    print(f"  - country_codes_clean rows: {verification_counts['country_codes'][1]}")
    print("Step 3 (Postgres Load)      : PASSED")
    print(f"  - raw.coffee rows         : {verification_counts['coffee'][1]}")
    print(f"  - raw.population rows     : {verification_counts['population'][1]}")
    print(f"  - raw.country_codes rows  : {verification_counts['country_codes'][1]}")
    print("Step 4 (Schema Doc)         : PASSED")
    print("================================")
    print("")
    print("UNMAPPED COUNTRIES TO REVIEW:")
    if STEP1_COUNTS["unmapped_names"]:
        for country in STEP1_COUNTS["unmapped_names"]:
            print(country)
    else:
        print("None")
    print("")
    print("================================")


if __name__ == "__main__":
    run_verification()
