# Housekeeping Scripts

Utility scripts for cleaning, normalizing, and managing Collins contract data.

## Scripts

### `clean_contract_ids.py`

Strips trailing sequence numbers from `CollinsOrOtherPartyContractID` values.

**Problem it solves:** Contract IDs like `ABC-MSA2-SOF 123` should be normalized to `ABC-MSA2-SOF`. This script finds every value matching that pattern and writes the cleaned version into a new adjacent column.

**Input:** Any `.xlsx` or `.csv` file containing a `CollinsOrOtherPartyContractID` column.

**Output:** A new file with `_cleaned` appended to the filename (e.g., `data_cleaned.xlsx`), with a `Cleaned CollinsOrOtherPartyContractID` column inserted immediately after the original.

### `copy_blobs_from_excel.py`

Reads blob paths from an Excel file and copies each blob to a new folder in Azure Blob Storage using a server-side copy (no local download).

**Problem it solves:** Bulk-copying a list of blobs to a new destination folder without manual Azure portal work.

**Input:** Any `.xlsx` file with a column of blob paths (defaults to `InputBlobPath` in a sheet named `license`).

**Output:** Each blob is copied to `{dest-folder}/{original-blob-path}` in the destination container, preserving the original folder structure under the new prefix.

**Arguments:**

| Argument | Required | Default | Description |
|---|---|---|---|
| `input_file` | yes | — | Path to the `.xlsx` file |
| `--account-url` | yes | — | Source storage account URL (e.g. `https://<account>.blob.core.windows.net`) |
| `--source-container` | yes | — | Source blob container name |
| `--dest-container` | yes | — | Destination blob container name |
| `--dest-folder` | yes | — | Folder prefix in the destination (e.g. `archive/2026`) |
| `--dest-account-url` | no | same as `--account-url` | Destination account URL for cross-account copies |
| `--sheet-name` | no | `license` | Sheet name in the Excel file |
| `--blob-path-col` | no | `InputBlobPath` | Column containing blob paths |
| `--dry-run` | no | off | Log what would be copied without copying |

Authentication uses `DefaultAzureCredential` — no secrets are passed on the command line. Ensure the identity running the script has the **Storage Blob Data Contributor** role on both the source and destination containers.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### `clean_contract_ids.py`

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

### `copy_blobs_from_excel.py`

```bash
# Dry-run first to verify paths without copying
python copy_blobs_from_excel.py license.xlsx \
  --account-url https://myaccount.blob.core.windows.net \
  --source-container mycontainer \
  --dest-container mycontainer \
  --dest-folder archive/2026 \
  --dry-run

# Real copy
python copy_blobs_from_excel.py license.xlsx \
  --account-url https://myaccount.blob.core.windows.net \
  --source-container mycontainer \
  --dest-container mycontainer \
  --dest-folder archive/2026
```

## Notes

- All columns are read as strings to avoid Excel auto-formatting issues.
- Rows that do not match the pattern are left unchanged (for `clean_contract_ids.py`).
- Place input files in an `input/` folder (gitignored) and outputs will land alongside them.
- `copy_blobs_from_excel.py` exits with code 1 if any blob copy fails; successfully copied blobs are not rolled back.
