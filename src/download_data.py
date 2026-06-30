from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

USDA_URL = "https://apps.fas.usda.gov/psdonline/downloads/psd_coffee_csv.zip"
USDA_MANUAL_URL = "https://apps.fas.usda.gov/psdonline/app/index.html#/app/downloads"
WORLD_BANK_URL = "https://api.worldbank.org/v2/en/indicator/SP.POP.TOTL?downloadformat=csv"
COUNTRY_CODES_URL = (
    "https://public.opendatasoft.com/explore/dataset/countries-codes/download/"
    "?format=csv&use_labels_for_header=true&delimiter=%3B"
)


def fetch(url: str, timeout: int = 60) -> bytes:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def extract_single_member(zip_bytes: bytes, target_path: Path, member_predicate) -> None:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        member_names = archive.namelist()
        member_name = next((name for name in member_names if member_predicate(name)), None)
        if member_name is None:
            raise FileNotFoundError(f"No matching file found in archive members: {member_names}")
        with archive.open(member_name) as source, target_path.open("wb") as destination:
            destination.write(source.read())


def download_usda_psd() -> None:
    target_path = RAW_DIR / "psd_coffee.csv"
    try:
        zip_bytes = fetch(USDA_URL)
        extract_single_member(
            zip_bytes,
            target_path,
            lambda name: name.lower().endswith(".csv"),
        )
        print(f"Downloaded USDA PSD coffee data to {target_path}")
    except Exception as exc:
        print("Failed to download USDA PSD coffee data.")
        print(f"Error: {exc}")
        print("Please download the dataset manually from:")
        print(f"  {USDA_MANUAL_URL}")
        print("Then extract the coffee CSV and place it at:")
        print(f"  {target_path}")


def download_world_bank_population() -> None:
    target_path = RAW_DIR / "world_population.csv"
    zip_bytes = fetch(WORLD_BANK_URL)
    extract_single_member(
        zip_bytes,
        target_path,
        lambda name: Path(name).name.startswith("API_SP.POP.TOTL_DS2_en_csv_v2")
        and name.lower().endswith(".csv"),
    )
    print(f"Downloaded World Bank population data to {target_path}")


def download_country_codes() -> None:
    target_path = RAW_DIR / "country_codes.csv"
    csv_bytes = fetch(COUNTRY_CODES_URL)
    target_path.write_bytes(csv_bytes)
    print(f"Downloaded country codes data to {target_path}")


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    download_usda_psd()
    download_world_bank_population()
    download_country_codes()
    return 0


if __name__ == "__main__":
    sys.exit(main())
