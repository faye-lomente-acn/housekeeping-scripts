import re
import sys
from pathlib import Path

import pandas as pd

COLUMN = "CollinsOrOtherPartyContractID"
CLEANED_COLUMN = "Cleaned CollinsOrOtherPartyContractID"

PPE_PATTERN = re.compile(r"PPE\d+=\d+", re.IGNORECASE)
ADSA_PATTERN = re.compile(r"ADSA#\s*A\d+", re.IGNORECASE)
NUMERIC_SUFFIX_PATTERN = re.compile(r"^(\d+),\s*\d+$")
FA_CONTRACT_PATTERN = re.compile(
    r"^([A-Z]{2}\d{4}-\d{2}-[A-Z]-\d{4})(-P\d+)?$", re.IGNORECASE
)


def clean_contract_id(value):
    if not isinstance(value, str):
        return value
    stripped = value.strip()

    adsa_match = ADSA_PATTERN.search(stripped)
    if adsa_match:
        return stripped[adsa_match.start() :].replace(";", ",")

    ppe_match = PPE_PATTERN.search(stripped)
    if ppe_match:
        return ppe_match.group(0).replace(";", ",")

    numeric_match = NUMERIC_SUFFIX_PATTERN.match(stripped)
    if numeric_match:
        return numeric_match.group(1).replace(";", ",")

    fa_match = FA_CONTRACT_PATTERN.match(stripped)
    if fa_match:
        return fa_match.group(1)

    return value


def process_file(input_path: str) -> Path:
    path = Path(input_path)
    ext = path.suffix.lower()

    if ext == ".xlsx":
        df = pd.read_excel(path, dtype=str)
    elif ext == ".csv":
        df = pd.read_csv(path, dtype=str)
    else:
        raise ValueError(f"Unsupported file format '{ext}'. Use .xlsx or .csv.")

    if COLUMN not in df.columns:
        raise ValueError(
            f"Column '{COLUMN}' not found. Available columns: {list(df.columns)}"
        )

    col_idx = df.columns.get_loc(COLUMN)
    cleaned = df[COLUMN].apply(clean_contract_id)
    matched = (cleaned != df[COLUMN]).sum()

    df.insert(col_idx + 1, CLEANED_COLUMN, cleaned)  # type: ignore

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{path.stem}_cleaned{path.suffix}"
    if ext == ".xlsx":
        df.to_excel(output_path, index=False)
    else:
        df.to_csv(output_path, index=False)

    print(f"Rows processed : {len(df)}")
    print(f"Pattern matched: {matched}")
    print(f"Output saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python clean_contract_ids.py <input_file.xlsx|input_file.csv>")
        sys.exit(1)
    try:
        process_file(sys.argv[1])
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        sys.exit(1)
