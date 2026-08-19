import difflib
import sys
from pathlib import Path

import pandas as pd

EXTRACTION_BLOB_COL = "InputBlobPath"
EXTRACTION_ROWKEY_COL = "RowKey"
EXTRACTION_NAME_COL = "CollinsLegalEntity1Name"
EXTRACTION_ADDRESS_COL = "CollinsLegalEntity1FullAddress"

MASTERLIST_NAME_COL = "Collins Legal Entity Company Name Visible in Dropdown"
MASTERLIST_ADDRESS_COL = "Collins Legal Entity Full Address"

SIMILARITY_THRESHOLD = 0.8
MULTIPLE_ADDRESSES = "Multiple Addresses"

OUTPUT_COLS = [
    EXTRACTION_BLOB_COL,
    EXTRACTION_ROWKEY_COL,
    EXTRACTION_NAME_COL,
    EXTRACTION_ADDRESS_COL,
    MASTERLIST_NAME_COL,
    MASTERLIST_ADDRESS_COL,
]


def fuzzy_score(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def load_extraction(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    required = [EXTRACTION_BLOB_COL, EXTRACTION_ROWKEY_COL, EXTRACTION_NAME_COL, EXTRACTION_ADDRESS_COL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Extraction file missing columns {missing}. Available: {list(df.columns)}")
    return df


def load_masterlist(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    required = [MASTERLIST_NAME_COL, MASTERLIST_ADDRESS_COL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Masterlist missing columns {missing}. Available: {list(df.columns)}")
    df[MASTERLIST_NAME_COL] = df[MASTERLIST_NAME_COL].str.strip()
    df[MASTERLIST_ADDRESS_COL] = df[MASTERLIST_ADDRESS_COL].str.strip()
    return df


def build_candidate_index(masterlist_df: pd.DataFrame) -> list:
    seen = set()
    candidates = []
    for name in masterlist_df[MASTERLIST_NAME_COL].dropna():
        if name not in seen:
            seen.add(name)
            candidates.append((name.lower(), name))
    return candidates


def find_best_name_match(query: str, candidates: list) -> tuple:
    normalized = query.strip().lower()
    if not normalized:
        return ("", 0.0)
    best_name, best_score = "", 0.0
    for norm_candidate, original in candidates:
        score = fuzzy_score(normalized, norm_candidate)
        if score > best_score:
            best_score = score
            best_name = original
    return (best_name, best_score)


def resolve_address(entity_name: str, masterlist_df: pd.DataFrame) -> str:
    rows = masterlist_df[masterlist_df[MASTERLIST_NAME_COL] == entity_name]
    addresses = rows[MASTERLIST_ADDRESS_COL].dropna()
    unique_normalized = addresses.str.strip().str.lower().unique()
    if len(unique_normalized) <= 1:
        first = addresses.iloc[0] if not addresses.empty else ""
        return first
    return MULTIPLE_ADDRESSES


def validate_entity(extraction_df: pd.DataFrame, masterlist_df: pd.DataFrame) -> pd.DataFrame:
    candidates = build_candidate_index(masterlist_df)
    records = []
    matched = 0
    below_threshold = 0
    null_name = 0

    for _, row in extraction_df.iterrows():
        base = {
            EXTRACTION_BLOB_COL: row[EXTRACTION_BLOB_COL],
            EXTRACTION_ROWKEY_COL: row[EXTRACTION_ROWKEY_COL],
            EXTRACTION_NAME_COL: row[EXTRACTION_NAME_COL],
            EXTRACTION_ADDRESS_COL: row[EXTRACTION_ADDRESS_COL],
            MASTERLIST_NAME_COL: "",
            MASTERLIST_ADDRESS_COL: "",
        }

        raw_name = row[EXTRACTION_NAME_COL]
        if not isinstance(raw_name, str) or not raw_name.strip():
            null_name += 1
            records.append(base)
            continue

        best_name, score = find_best_name_match(raw_name, candidates)

        if score < SIMILARITY_THRESHOLD:
            below_threshold += 1
            records.append(base)
            continue

        matched += 1
        base[MASTERLIST_NAME_COL] = best_name
        base[MASTERLIST_ADDRESS_COL] = resolve_address(best_name, masterlist_df)
        records.append(base)

    print(f"Extraction rows       : {len(extraction_df)}")
    print(f"Matched (>= {SIMILARITY_THRESHOLD:.2f})     : {matched}")
    print(f"Below threshold       : {below_threshold}")
    print(f"Null name (skipped)   : {null_name}")

    return pd.DataFrame(records, columns=OUTPUT_COLS)


def run(extraction_path: str, masterlist_path: str) -> Path:
    extraction_df = load_extraction(extraction_path)
    masterlist_df = load_masterlist(masterlist_path)

    output_df = validate_entity(extraction_df, masterlist_df)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{Path(extraction_path).stem}_validated.xlsx"
    output_df.to_excel(output_path, index=False)

    print(f"Output saved to       : {output_path}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python validate_collins_legal_entity.py <attribute-extraction.xlsx> <masterlist.xlsx>")
        sys.exit(1)
    try:
        run(sys.argv[1], sys.argv[2])
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        sys.exit(1)
