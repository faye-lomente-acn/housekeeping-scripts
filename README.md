# Housekeeping Scripts

Utility scripts for cleaning and normalizing Collins contract data.

## Scripts

### `clean_contract_ids.py`

Strips trailing sequence numbers from `CollinsOrOtherPartyContractID` values.

**Problem it solves:** Contract IDs like `ABC-MSA2-SOF 123` should be normalized to `ABC-MSA2-SOF`. This script finds every value matching that pattern and writes the cleaned version into a new adjacent column.

**Input:** Any `.xlsx` or `.csv` file containing a `CollinsOrOtherPartyContractID` column.

**Output:** A new file with `_cleaned` appended to the filename (e.g., `data_cleaned.xlsx`), with a `Cleaned CollinsOrOtherPartyContractID` column inserted immediately after the original.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install pandas openpyxl
```

## Usage

```bash
python clean_contract_ids.py <input_file.xlsx|input_file.csv>
```

Example:

```bash
python clean_contract_ids.py input\contracts.xlsx
# Output: input\contracts_cleaned.xlsx
```

The script prints a summary on completion:

```
Rows processed : 500
Pattern matched: 312
Output saved to: input\contracts_cleaned.xlsx
```

## Notes

- All columns are read as strings to avoid Excel auto-formatting issues.
- Rows that do not match the pattern are left unchanged.
- Place input files in an `input/` folder (gitignored) and outputs will land alongside them.
