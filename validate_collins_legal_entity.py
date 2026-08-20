import argparse
import difflib
import re
import sys
from pathlib import Path

import pandas as pd

EXTRACTION_BLOB_COL = "InputBlobPath"
EXTRACTION_ROWKEY_COL = "RowKey"
EXTRACTION_NAME_COL = "CollinsLegalEntity1Name"
EXTRACTION_ADDRESS_COL = "CollinsLegalEntity1FullAddress"

UNIQUE_VALUES_NAME_COL = "CollinsLegalEntity1Name"
UNIQUE_VALUES_MAPPED_COL = "To be mapped Collins Legal Entity"

ICM_DROPDOWN_COL = "Collins Legal Entity Company Name Visible in Dropdown"
ICM_ADDRESS_COL = "Collins Legal Entity Full Address"

MULTIPLE_ADDRESSES = "Multiple Addresses"

DIFF_COL = "Different from Extracted"

_KNOWN_COUNTRIES = frozenset({
    "united states", "usa", "us", "canada", "mexico",
    "united kingdom", "uk", "gb", "great britain",
    "england", "scotland", "wales", "northern ireland",
    "germany", "france", "italy", "spain", "netherlands",
    "holland", "belgium", "switzerland", "austria",
    "ireland", "luxembourg", "portugal", "denmark",
    "sweden", "norway", "finland",
    "poland", "czech republic", "czechia", "slovakia",
    "hungary", "romania", "bulgaria", "croatia",
    "serbia", "ukraine", "greece",
    "israel", "saudi arabia", "uae", "united arab emirates",
    "turkey", "egypt", "south africa", "qatar", "kuwait", "bahrain", "jordan",
    "india", "china", "japan", "south korea", "korea",
    "singapore", "australia", "new zealand",
    "malaysia", "thailand", "indonesia", "philippines",
    "taiwan", "hong kong", "vietnam",
    "brazil", "argentina", "colombia", "chile", "peru",
})

_US_STATES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
})

_ZIP_PATTERNS = [
    re.compile(r"\d{5}(-\d{4})?"),                      # US: 12345 or 12345-6789
    re.compile(r"[a-z]{1,2}\d[a-z\d]?\s?\d[a-z]{2}"),  # UK: sw1a 2aa
    re.compile(r"[a-z]\d[a-z]\s?\d[a-z]\d"),            # Canada: a1b 2c3
    re.compile(r"\d{4}\s[a-z]{2}"),                     # Netherlands: 1234 ab
    re.compile(r"\d{4,6}"),                              # General: AU/NZ/BE/AT/CH
]

_RE_STATE_ZIP_COMBO = re.compile(r"^([a-z]{2})\s+(\d{5}(?:-\d{4})?)$")

_COMPONENT_WEIGHTS = {"zip": 0.35, "country": 0.20, "state": 0.10, "remainder": 0.35}

# Country and state are well-defined codes — partial fuzzy credit would let
# "United Kingdom" vs "United States" score near 1.0. Exact match only.
_EXACT_MATCH_COMPONENTS = {"country", "state"}

OUTPUT_COLS = [
    EXTRACTION_BLOB_COL,
    EXTRACTION_ROWKEY_COL,
    EXTRACTION_NAME_COL,
    EXTRACTION_ADDRESS_COL,
    ICM_DROPDOWN_COL,
    ICM_ADDRESS_COL,
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
    required = [ICM_DROPDOWN_COL, ICM_ADDRESS_COL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"ICM sheet missing columns {missing}. Available: {list(df.columns)}"
        )
    df[ICM_DROPDOWN_COL] = df[ICM_DROPDOWN_COL].str.strip()
    df[ICM_ADDRESS_COL] = df[ICM_ADDRESS_COL].str.strip()
    return df


def _normalize_address(text: str) -> str:
    text = re.sub(r"[\r\n]+", ", ", text.strip())
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    return text.strip().lower()


def _parse_address_components(address: str) -> dict:
    tokens = [t.strip() for t in address.split(",") if t.strip()]
    used = set()
    zip_val = country_val = state_val = ""

    for i in range(len(tokens) - 1, -1, -1):
        tok = tokens[i]

        if not country_val and tok in _KNOWN_COUNTRIES:
            country_val = tok
            used.add(i)
            continue

        if not zip_val or not state_val:
            m = _RE_STATE_ZIP_COMBO.fullmatch(tok)
            if m and m.group(1).upper() in _US_STATES:
                if not state_val:
                    state_val = m.group(1)
                if not zip_val:
                    zip_val = m.group(2)
                used.add(i)
                continue

        if not zip_val:
            if any(p.fullmatch(tok) for p in _ZIP_PATTERNS):
                zip_val = tok
                used.add(i)
                continue

        if not state_val and len(tok) == 2 and tok.upper() in _US_STATES:
            state_val = tok
            used.add(i)

    remainder = ", ".join(t for j, t in enumerate(tokens) if j not in used)
    return {"zip": zip_val, "country": country_val, "state": state_val, "remainder": remainder}


def _component_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def address_similarity(a: str, b: str) -> float:
    norm_a = _normalize_address(a)
    norm_b = _normalize_address(b)
    comp_a = _parse_address_components(norm_a)
    comp_b = _parse_address_components(norm_b)

    if all(not v for v in comp_a.values()) and all(not v for v in comp_b.values()):
        return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()

    total_weight = 0.0
    weighted_sum = 0.0
    for key, weight in _COMPONENT_WEIGHTS.items():
        val_a = comp_a[key]
        val_b = comp_b[key]
        if not val_a and not val_b:
            continue
        total_weight += weight
        if key in _EXACT_MATCH_COMPONENTS:
            sim = 1.0 if val_a == val_b else 0.0
        else:
            sim = _component_similarity(val_a, val_b)
        weighted_sum += weight * sim

    if total_weight == 0.0:
        return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()

    return weighted_sum / total_weight


def compute_diff_col(name: str, extracted: str, icm: str) -> str:
    has_name = isinstance(name, str) and bool(name.strip())
    a = extracted.strip() if isinstance(extracted, str) else ""
    b = icm.strip() if isinstance(icm, str) else ""
    if not has_name and not a and not b:
        return ""
    if has_name and not a and not b:
        return "Empty Address"
    if b == MULTIPLE_ADDRESSES:
        return "Yes"
    ratio = address_similarity(a, b)
    return "No" if ratio >= 0.85 else "Yes"


def lookup_mapped_name(extracted_name: str, unique_values_df: pd.DataFrame) -> str:
    normalized = extracted_name.strip().lower()
    if not normalized:
        return ""
    match = unique_values_df[
        unique_values_df[UNIQUE_VALUES_NAME_COL].str.lower() == normalized
    ]
    if match.empty:
        return ""
    value = match.iloc[0][UNIQUE_VALUES_MAPPED_COL]
    return value if isinstance(value, str) else ""


def resolve_icm(mapped_name: str, icm_df: pd.DataFrame) -> tuple:
    normalized = mapped_name.strip().lower()
    rows = icm_df[icm_df[ICM_DROPDOWN_COL].str.lower() == normalized]
    if rows.empty:
        return ("", "")
    canonical_name = rows.iloc[0][ICM_DROPDOWN_COL]
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
            ICM_DROPDOWN_COL: "",
            ICM_ADDRESS_COL: "",
            DIFF_COL: "",
        }

        raw_name = row[EXTRACTION_NAME_COL]
        if not isinstance(raw_name, str) or not raw_name.strip():
            null_name += 1
            base[DIFF_COL] = compute_diff_col(base[EXTRACTION_NAME_COL], base[EXTRACTION_ADDRESS_COL], base[ICM_ADDRESS_COL])
            records.append(base)
            continue

        mapped_name = lookup_mapped_name(raw_name, unique_values_df)
        if not mapped_name:
            hop1_misses += 1
            base[DIFF_COL] = compute_diff_col(base[EXTRACTION_NAME_COL], base[EXTRACTION_ADDRESS_COL], base[ICM_ADDRESS_COL])
            records.append(base)
            continue

        canonical_name, address = resolve_icm(mapped_name, icm_df)
        if not canonical_name:
            hop2_misses += 1
            base[DIFF_COL] = compute_diff_col(base[EXTRACTION_NAME_COL], base[EXTRACTION_ADDRESS_COL], base[ICM_ADDRESS_COL])
            records.append(base)
            continue

        matched += 1
        base[ICM_DROPDOWN_COL] = canonical_name
        base[ICM_ADDRESS_COL] = address
        base[DIFF_COL] = compute_diff_col(base[EXTRACTION_NAME_COL], base[EXTRACTION_ADDRESS_COL], base[ICM_ADDRESS_COL])
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
