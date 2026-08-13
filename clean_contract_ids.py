import re
import sys
from pathlib import Path

import pandas as pd

COLUMN = "CollinsOrOtherPartyContractID"
CLEANED_COLUMN = "Cleaned CollinsOrOtherPartyContractID"

# Finds {prefix} [-] MSA[2]-SOF anywhere in a string.
# Handles: surrounding text, spaces around dash, missing dash, MSA-SOF vs MSA2-SOF.
PATTERN = re.compile(r"([\w+]+)\s*-?\s*(MSA\d*-SOF)", re.IGNORECASE)


def clean_contract_id(value):
    if not isinstance(value, str):
        return value
    match = PATTERN.search(value.strip())
    if match:
        prefix = match.group(1).rstrip("+")
        suffix = match.group(2).upper()
        return f"{prefix}-{suffix}"
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

    output_dir = path.parent / "output"
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
