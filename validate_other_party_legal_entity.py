import argparse
import difflib
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

EXTRACTION_BLOB_COL = "InputBlobPath"
EXTRACTION_ROWKEY_COL = "RowKey"
EXTRACTION_NAME_COL = "OtherPartyLegalEntity1Name"
EXTRACTION_ADDRESS_COL = "OtherParty1FullAddress"

MASTERLIST_NAME_COL = "Other Party Company Name"
MASTERLIST_ADDRESS_COL = "Other Party Full Address"

OUT_NAME_COL = "Other Party Legal Entity Company Name From Masterlist"
OUT_ADDRESS_COL = "Other Party Legal Entity Company Full Address From Masterlist"

DIFF_COL = "Different from Extracted"

OUTPUT_COLS = [
    EXTRACTION_BLOB_COL,
    EXTRACTION_ROWKEY_COL,
    EXTRACTION_NAME_COL,
    EXTRACTION_ADDRESS_COL,
    OUT_NAME_COL,
    OUT_ADDRESS_COL,
    DIFF_COL,
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


def load_masterlist(path: str, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, dtype=str)
    required = [MASTERLIST_NAME_COL, MASTERLIST_ADDRESS_COL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Masterlist sheet missing columns {missing}. Available: {list(df.columns)}"
        )
    df[MASTERLIST_NAME_COL] = df[MASTERLIST_NAME_COL].str.strip()
    df[MASTERLIST_ADDRESS_COL] = df[MASTERLIST_ADDRESS_COL].str.strip()
    return df


def normalize_address(addr: str) -> str:
    addr = addr.lower().strip()
    addr = re.sub(r",?\s*(united states|u\.?s\.?a?)\s*$", "", addr)
    addr = re.sub(r",\s*", ", ", addr).strip(", ")
    addr = re.sub(r"\s+", " ", addr)
    return addr


def compute_diff_col(name: str, extracted: str, masterlist: str) -> str:
    has_name = isinstance(name, str) and bool(name.strip())
    a = extracted.strip() if isinstance(extracted, str) else ""
    b = masterlist.strip() if isinstance(masterlist, str) else ""
    if not has_name and not a and not b:
        return ""
    if has_name and not a and not b:
        return "Empty Address"
    ratio = difflib.SequenceMatcher(
        None, normalize_address(a), normalize_address(b)
    ).ratio()
    return "No" if ratio >= 0.80 else "Yes"


def lookup_other_party(name: str, masterlist_df: pd.DataFrame) -> tuple:
    normalized = name.strip().lower()
    if not normalized:
        return ("", "")
    match = masterlist_df[masterlist_df[MASTERLIST_NAME_COL].str.lower() == normalized]
    if match.empty:
        return ("", "")
    return (match.iloc[0][MASTERLIST_NAME_COL], match.iloc[0][MASTERLIST_ADDRESS_COL])


def validate_entity(
    extraction_df: pd.DataFrame, masterlist_df: pd.DataFrame
) -> pd.DataFrame:
    records = []
    matched = 0
    misses = 0
    null_name = 0

    total = len(extraction_df)
    for i, (_, row) in enumerate(extraction_df.iterrows(), start=1):
        if i == 1 or i % 500 == 0 or i == total:
            logger.info(f"  Processing row {i}/{total}...")
        base = {
            EXTRACTION_BLOB_COL: row[EXTRACTION_BLOB_COL],
            EXTRACTION_ROWKEY_COL: row[EXTRACTION_ROWKEY_COL],
            EXTRACTION_NAME_COL: row[EXTRACTION_NAME_COL],
            EXTRACTION_ADDRESS_COL: row[EXTRACTION_ADDRESS_COL],
            OUT_NAME_COL: "",
            OUT_ADDRESS_COL: "",
            DIFF_COL: "",
        }

        raw_name = row[EXTRACTION_NAME_COL]
        if not isinstance(raw_name, str) or not raw_name.strip():
            null_name += 1
            base[DIFF_COL] = compute_diff_col(
                base[EXTRACTION_NAME_COL],
                base[EXTRACTION_ADDRESS_COL],
                base[OUT_ADDRESS_COL],
            )
            records.append(base)
            continue

        canonical_name, address = lookup_other_party(raw_name, masterlist_df)
        if not canonical_name:
            misses += 1
            base[DIFF_COL] = compute_diff_col(
                base[EXTRACTION_NAME_COL],
                base[EXTRACTION_ADDRESS_COL],
                base[OUT_ADDRESS_COL],
            )
            records.append(base)
            continue

        matched += 1
        base[OUT_NAME_COL] = canonical_name
        base[OUT_ADDRESS_COL] = address
        base[DIFF_COL] = compute_diff_col(
            base[EXTRACTION_NAME_COL],
            base[EXTRACTION_ADDRESS_COL],
            base[OUT_ADDRESS_COL],
        )
        records.append(base)

    logger.info(f"Extraction rows  : {len(extraction_df)}")
    logger.info(f"Matched          : {matched}")
    logger.info(f"No match         : {misses}")
    logger.info(f"Null name        : {null_name}")

    return pd.DataFrame(records, columns=OUTPUT_COLS)


def run(
    extraction_path: str,
    extraction_sheet: str,
    masterlist_path: str,
    masterlist_sheet: str,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info("=" * 50)
    logger.info("Other Party Legal Entity Validator")
    logger.info(f"Extraction : {extraction_path}  [{extraction_sheet}]")
    logger.info(f"Masterlist : {masterlist_path}  [{masterlist_sheet}]")
    logger.info("=" * 50)

    logger.info("Loading extraction file...")
    extraction_df = load_extraction(extraction_path, extraction_sheet)
    logger.info(f"  {len(extraction_df)} rows loaded.")

    logger.info("Loading masterlist (ICM Customer)...")
    masterlist_df = load_masterlist(masterlist_path, masterlist_sheet)
    logger.info(f"  {len(masterlist_df)} rows loaded.")

    logger.info("Running validation...")
    output_df = validate_entity(extraction_df, masterlist_df)

    metadata = pd.DataFrame(
        [
            {"Key": "Run Timestamp", "Value": timestamp},
            {"Key": "Extraction File", "Value": str(extraction_path)},
            {"Key": "Masterlist File", "Value": str(masterlist_path)},
            {"Key": "Extraction Name Column", "Value": EXTRACTION_NAME_COL},
            {"Key": "Extraction Address Column", "Value": EXTRACTION_ADDRESS_COL},
            {"Key": "Masterlist Name Column", "Value": MASTERLIST_NAME_COL},
            {"Key": "Masterlist Address Column", "Value": MASTERLIST_ADDRESS_COL},
            {"Key": "Output Name Column", "Value": OUT_NAME_COL},
            {"Key": "Output Address Column", "Value": OUT_ADDRESS_COL},
        ]
    )

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{EXTRACTION_NAME_COL}_{timestamp}.xlsx"
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        output_df.to_excel(writer, sheet_name="Results", index=False)
        metadata.to_excel(writer, sheet_name="Metadata", index=False)

    logger.info(f"Output saved to  : {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate Other Party Legal Entity names and addresses against the masterlist."
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
        "--masterlist-sheet",
        default="ICMCustomerLegalEntityMaster",
        help="Sheet name for the ICM customer master data (default: 'ICMCustomerLegalEntityMaster').",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        run(
            args.extraction,
            args.extraction_sheet,
            args.masterlist,
            args.masterlist_sheet,
        )
    except (ValueError, FileNotFoundError) as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
