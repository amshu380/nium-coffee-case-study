from __future__ import annotations

import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DUMP_PATH = PROJECT_ROOT / "db_dump" / "nium_coffee.sql"

TABLES = [
    "raw.country_codes",
    "raw.coffee",
    "raw.population",
    "analytics.dim_country",
    "analytics.fact_coffee",
    "analytics.fact_population",
]

VIEWS = [
    "v_country_year_metrics",
    "v_country_growth_metrics",
    "v_latest_year_snapshot",
    "v_global_trends",
    "v_market_attractiveness",
    "v_top_market_candidates",
]

PRIMARY_KEYS = {
    "analytics.dim_country": ["iso3_code"],
    "analytics.fact_coffee": ["iso3_code", "market_year"],
    "analytics.fact_population": ["iso3_code", "year"],
}

FOREIGN_KEYS = [
    (
        "analytics.fact_coffee",
        "fk_fact_coffee_dim_country",
        ["iso3_code"],
        "analytics.dim_country",
        ["iso3_code"],
    ),
    (
        "analytics.fact_population",
        "fk_fact_population_dim_country",
        ["iso3_code"],
        "analytics.dim_country",
        ["iso3_code"],
    ),
]

INDEX_STATEMENTS = [
    "CREATE INDEX idx_fact_coffee_iso3 ON analytics.fact_coffee (iso3_code);",
    "CREATE INDEX idx_fact_coffee_year ON analytics.fact_coffee (market_year);",
    "CREATE INDEX idx_fact_pop_iso3 ON analytics.fact_population (iso3_code);",
    "CREATE INDEX idx_fact_pop_year ON analytics.fact_population (year);",
    "CREATE INDEX idx_dim_country_iso3 ON analytics.dim_country (iso3_code);",
]


def load_engine():
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(database_url, pool_pre_ping=True)


def normalize_type(data_type: str, udt_name: str) -> str:
    value = (data_type or "").lower()
    udt = (udt_name or "").lower()
    if value in {"text", "character varying", "character", "varchar"}:
        return "TEXT"
    if value in {"integer", "smallint"} or udt in {"int4", "int2"}:
        return "INTEGER"
    if value == "bigint" or udt == "int8":
        return "BIGINT"
    if value in {"double precision", "real", "numeric", "decimal"} or udt in {"float8", "float4", "numeric"}:
        return "NUMERIC"
    return "TEXT"


def escape_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def format_value(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "NULL"
        return format(value, ".15g")
    if hasattr(value, "item"):
        try:
            return format_value(value.item())
        except Exception:
            pass
    if isinstance(value, (int, bool)):
        return str(int(value)) if isinstance(value, bool) else str(value)
    return escape_text(str(value))


def get_table_columns(conn, table_name: str):
    schema, name = table_name.split(".")
    query = text(
        """
        SELECT column_name, data_type, udt_name, is_nullable, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        ORDER BY ordinal_position
        """
    )
    return conn.execute(query, {"schema": schema, "table": name}).mappings().all()


def get_row_count(conn, table_name: str) -> int:
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())


def get_view_definition(conn, view_name: str) -> str:
    definition = conn.execute(text(f"SELECT pg_get_viewdef('analytics.{view_name}'::regclass, true)")).scalar_one()
    return definition.strip().rstrip(";")


def split_sql_statements(sql_text: str) -> list[str]:
    statements = []
    buf = []
    in_single = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(sql_text):
        ch = sql_text[i]
        nxt = sql_text[i + 1] if i + 1 < len(sql_text) else ""
        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                i += 2
                in_block_comment = False
            else:
                i += 1
            continue
        if in_single:
            buf.append(ch)
            if ch == "'":
                if nxt == "'":
                    buf.append(nxt)
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        if ch == "-" and nxt == "-":
            buf.append(ch)
            buf.append(nxt)
            i += 2
            in_line_comment = True
            continue
        if ch == "/" and nxt == "*":
            buf.append(ch)
            buf.append(nxt)
            i += 2
            in_block_comment = True
            continue
        if ch == "'":
            buf.append(ch)
            in_single = True
            i += 1
            continue
        if ch == ";":
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement + ";")
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    trailing = "".join(buf).strip()
    if trailing:
        statements.append(trailing)
    return statements


def count_insert_rows(statement: str) -> int:
    upper = statement.upper()
    if not upper.startswith("INSERT INTO "):
        return 0
    idx = upper.find("VALUES")
    if idx == -1:
        return 0
    s = statement[idx + len("VALUES"):].strip().rstrip(";")
    count = 0
    depth = 0
    in_single = False
    i = 0
    while i < len(s):
        ch = s[i]
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if in_single:
            if ch == "'":
                if nxt == "'":
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        if ch == "'":
            in_single = True
            i += 1
            continue
        if ch == "(":
            if depth == 0:
                count += 1
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        i += 1
    return count


def strip_leading_comments(statement: str) -> str:
    lines = statement.strip().splitlines()
    kept = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if in_block:
            if '*/' in stripped:
                in_block = False
            continue
        if not stripped:
            continue
        if stripped.startswith('--'):
            continue
        if stripped.startswith('/*'):
            if '*/' not in stripped:
                in_block = True
            continue
        kept.append(stripped)
    return ' '.join(kept)


def statement_kind(statement: str) -> str:
    normalized = strip_leading_comments(statement).upper()
    if normalized.startswith("CREATE TABLE"):
        return "CREATE TABLE"
    if normalized.startswith("CREATE OR REPLACE VIEW"):
        return "CREATE VIEW"
    if normalized.startswith("INSERT INTO"):
        return "INSERT"
    if normalized.startswith("ALTER TABLE"):
        return "ALTER TABLE"
    if normalized.startswith("CREATE INDEX"):
        return "CREATE INDEX"
    return "OTHER"


def insert_table_dump(conn, out, table_name: str, live_counts: dict[str, int]) -> None:
    schema, name = table_name.split(".")
    columns = list(get_table_columns(conn, table_name))
    column_names = [col["column_name"] for col in columns]
    out.write(f"-- Table: {table_name}\n")
    out.write(f"CREATE TABLE {table_name} (\n")
    defs = []
    for col in columns:
        col_type = normalize_type(col["data_type"], col["udt_name"])
        nullable = " NOT NULL" if col["is_nullable"] == "NO" else ""
        defs.append(f"    {col['column_name']} {col_type}{nullable}")
    out.write(",\n".join(defs))
    out.write("\n);\n\n")

    out.write("BEGIN;\n")
    result = conn.exec_driver_sql(f"SELECT * FROM {table_name}")
    keys = list(result.keys())
    batch = []
    row_count = 0
    for row in result:
        values = []
        for value in row:
            values.append(format_value(value))
        batch.append("(" + ", ".join(values) + ")")
        row_count += 1
        if len(batch) == 500:
            out.write(f"INSERT INTO {table_name} ({', '.join(keys)}) VALUES\n")
            out.write(",\n".join(batch))
            out.write(";\n")
            batch = []
    if batch:
        out.write(f"INSERT INTO {table_name} ({', '.join(keys)}) VALUES\n")
        out.write(",\n".join(batch))
        out.write(";\n")
    out.write("COMMIT;\n\n")
    live_counts[table_name] = row_count


def main() -> int:
    DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = load_engine()
    live_counts: dict[str, int] = {}
    with engine.connect() as conn, DUMP_PATH.open("w", encoding="utf-8", newline="\n") as out:
        out.write("-- Nium Coffee Case Study PostgreSQL Dump\n")
        out.write(f"-- Generated at: {datetime.now(timezone.utc).isoformat()}\n")
        out.write("-- Source: Hosted PostgreSQL database referenced by DATABASE_URL in .env\n")
        out.write("-- Restore: psql -d <database_name> -f db_dump/nium_coffee.sql\n\n")
        out.write("DROP SCHEMA IF EXISTS analytics CASCADE;\n")
        out.write("DROP SCHEMA IF EXISTS raw CASCADE;\n\n")
        out.write("CREATE SCHEMA raw;\n")
        out.write("CREATE SCHEMA analytics;\n\n")

        for table_name in TABLES:
            insert_table_dump(conn, out, table_name, live_counts)

        out.write("-- Primary keys\n")
        for table_name, columns in PRIMARY_KEYS.items():
            constraint_name = table_name.split(".")[1] + "_pkey"
            out.write(
                f"ALTER TABLE {table_name} ADD CONSTRAINT {constraint_name} PRIMARY KEY ({', '.join(columns)});\n"
            )
        out.write("\n-- Foreign keys\n")
        for table_name, constraint_name, cols, ref_table, ref_cols in FOREIGN_KEYS:
            out.write(
                f"ALTER TABLE {table_name} ADD CONSTRAINT {constraint_name} FOREIGN KEY ({', '.join(cols)}) REFERENCES {ref_table} ({', '.join(ref_cols)});\n"
            )
        out.write("\n-- Indexes\n")
        for stmt in INDEX_STATEMENTS:
            out.write(stmt + "\n")
        out.write("\n-- Views\n")
        for view_name in VIEWS:
            definition = get_view_definition(conn, view_name)
            out.write(f"CREATE OR REPLACE VIEW analytics.{view_name} AS\n{definition};\n\n")
        out.write("-- ANALYZE/VACUUM note: run ANALYZE after restore if needed.\n")

    sql_text = DUMP_PATH.read_text(encoding="utf-8")
    statements = split_sql_statements(sql_text)
    kinds = Counter(statement_kind(stmt) for stmt in statements)
    dump_counts = defaultdict(int)
    for stmt in statements:
        normalized = stmt.strip()
        upper = normalized.upper()
        if upper.startswith("INSERT INTO "):
            table_name = normalized.split()[2]
            dump_counts[table_name] += count_insert_rows(stmt)

    print(f"Wrote dump: {DUMP_PATH}")
    print(f"File size bytes: {DUMP_PATH.stat().st_size}")
    print(f"Statement counts: {dict(kinds)}")
    print("Dump row counts:")
    for table_name in TABLES:
        print(f"  {table_name}: dump={dump_counts[table_name]}, live={live_counts[table_name]}")
    print("Validation mode: structural SQL parse (restore execution skipped to avoid mutating the hosted database).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
