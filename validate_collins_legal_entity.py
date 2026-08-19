import argparse
import sys
from pathlib import Path

import pandas as pd

EXTRACTION_BLOB_COL = "InputBlobPath"
EXTRACTION_ROWKEY_COL = "RowKey"
EXTRACTION_NAME_COL = "CollinsLegalEntity1Name"
EXTRACTION_ADDRESS_COL = "CollinsLegalEntity1FullAddress"

UNIQUE_VALUES_NAME_COL = "CollinsLegalEntity1Name"
UNIQUE_VALUES_MAPPED_COL = "To be mapped Collins Legal Entity"

ICM_DROPDOWN_COL = "Legal Entity Company Name Visible in Dropdown"
ICM_CANONICAL_NAME_COL = "Collins Legal Entity Company Name Visible in Dropdown"
ICM_ADDRESS_COL = "Collins Legal Entity Full Address"

MULTIPLE_ADDRESSES = "Multiple Addresses"

OUTPUT_COLS = [
    EXTRACTION_BLOB_COL,
    EXTRACTION_ROWKEY_COL,
    EXTRACTION_NAME_COL,
    EXTRACTION_ADDRESS_COL,
    ICM_CANONICAL_NAME_COL,
    ICM_ADDRESS_COL,
]


def load_extraction(path: str, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, dtype=str)
    required = [
        EXTRACTION_BLOB_COL,
        EXTRACTION_ROWKEY_COL,
        EXTRACTION_NAME_COL,
        EXTRACTION_ADDRESS_COL,
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Extraction file missing columns {missing}. Available: {list(df.columns)}"
        )
    return df


def load_unique_values(path: str, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, dtype=str)
    required = [UNIQUE_VALUES_NAME_COL, UNIQUE_VALUES_MAPPED_COL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Unique values sheet missing columns {missing}. Available: {list(df.columns)}"
        )
    df[UNIQUE_VALUES_NAME_COL] = df[UNIQUE_VALUES_NAME_COL].str.strip()
    df[UNIQUE_VALUES_MAPPED_COL] = df[UNIQUE_VALUES_MAPPED_COL].str.strip()
    return df


def load_icm(path: str, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, dtype=str)
    required = [ICM_DROPDOWN_COL, ICM_CANONICAL_NAME_COL, ICM_ADDRESS_COL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"ICM sheet missing columns {missing}. Available: {list(df.columns)}"
        )
    df[ICM_DROPDOWN_COL] = df[ICM_DROPDOWN_COL].str.strip()
    df[ICM_CANONICAL_NAME_COL] = df[ICM_CANONICAL_NAME_COL].str.strip()
    df[ICM_ADDRESS_COL] = df[ICM_ADDRESS_COL].str.strip()
    return df


def lookup_mapped_name(extracted_name: str, unique_values_df: pd.DataFrame) -> str:
    normalized = extracted_name.strip().lower()
    if not normalized:
        return ""
    match = unique_values_df[
        unique_values_df[UNIQUE_VALUES_NAME_COL].str.lower() == normalized
    ]
    if match.empty:
        return ""
    return match.iloc[0][UNIQUE_VALUES_MAPPED_COL]


def resolve_icm(mapped_name: str, icm_df: pd.DataFrame) -> tuple:
    normalized = mapped_name.strip().lower()
    rows = icm_df[icm_df[ICM_DROPDOWN_COL].str.lower() == normalized]
    if rows.empty:
        return ("", "")
    canonical_name = rows.iloc[0][ICM_CANONICAL_NAME_COL]
    unique_addresses = rows[ICM_ADDRESS_COL].dropna().str.strip().str.lower().unique()
    if len(unique_addresses) <= 1:
        address = (
            rows[ICM_ADDRESS_COL].dropna().iloc[0]
            if not rows[ICM_ADDRESS_COL].dropna().empty
            else ""
        )
    else:
        address = MULTIPLE_ADDRESSES
    return (canonical_name, address)


def validate_entity(
    extraction_df: pd.DataFrame, unique_values_df: pd.DataFrame, icm_df: pd.DataFrame
) -> pd.DataFrame:
    records = []
    matched = 0
    hop1_misses = 0
    hop2_misses = 0
    null_name = 0

    for _, row in extraction_df.iterrows():
        base = {
            EXTRACTION_BLOB_COL: row[EXTRACTION_BLOB_COL],
            EXTRACTION_ROWKEY_COL: row[EXTRACTION_ROWKEY_COL],
            EXTRACTION_NAME_COL: row[EXTRACTION_NAME_COL],
            EXTRACTION_ADDRESS_COL: row[EXTRACTION_ADDRESS_COL],
            ICM_CANONICAL_NAME_COL: "",
            ICM_ADDRESS_COL: "",
        }

        raw_name = row[EXTRACTION_NAME_COL]
        if not isinstance(raw_name, str) or not raw_name.strip():
            null_name += 1
            records.append(base)
            continue

        mapped_name = lookup_mapped_name(raw_name, unique_values_df)
        if not mapped_name:
            hop1_misses += 1
            records.append(base)
            continue

        canonical_name, address = resolve_icm(mapped_name, icm_df)
        if not canonical_name:
            hop2_misses += 1
            records.append(base)
            continue

        matched += 1
        base[ICM_CANONICAL_NAME_COL] = canonical_name
        base[ICM_ADDRESS_COL] = address
        records.append(base)

    print(f"Extraction rows       : {len(extraction_df)}")
    print(f"Matched               : {matched}")
    print(f"No unique values match: {hop1_misses}")
    print(f"No ICM match          : {hop2_misses}")
    print(f"Null name (skipped)   : {null_name}")

    return pd.DataFrame(records, columns=OUTPUT_COLS)


def run(
    extraction_path: str,
    extraction_sheet: str,
    masterlist_path: str,
    unique_values_sheet: str,
    icm_sheet: str,
) -> Path:
    extraction_df = load_extraction(extraction_path, extraction_sheet)
    unique_values_df = load_unique_values(masterlist_path, unique_values_sheet)
    icm_df = load_icm(masterlist_path, icm_sheet)

    output_df = validate_entity(extraction_df, unique_values_df, icm_df)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{Path(extraction_path).stem}_validated.xlsx"
    output_df.to_excel(output_path, index=False)

    print(f"Output saved to       : {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate Collins Legal Entity names and addresses against the masterlist."
    )
    parser.add_argument(
        "extraction", help="Path to the attribute extraction Excel file."
    )
    parser.add_argument("masterlist", help="Path to the masterlist Excel file.")
    parser.add_argument(
        "--extraction-sheet",
        default="Execution Report",
        help="Sheet name in the extraction file (default: 'Execution Report').",
    )
    parser.add_argument(
        "--unique-values-sheet",
        default="Collins Legal Unique values",
        help="Sheet name for the unique values mapping (default: 'Collins Legal Unique Values').",
    )
    parser.add_argument(
        "--masterlist-sheet",
        default="ICMCollinsLegalEntityMaster",
        help="Sheet name for the ICM master data (default: 'ICMCollinsLegalEntityMaster').",
    )
    args = parser.parse_args()
    try:
        run(
            args.extraction,
            args.extraction_sheet,
            args.masterlist,
            args.unique_values_sheet,
            args.masterlist_sheet,
        )
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        sys.exit(1)
