import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

DEFAULT_SHEET_NAME = "license"
DEFAULT_BLOB_PATH_COL = "InputBlobPath"

logger = logging.getLogger(__name__)


def load_blob_paths(path: str, sheet_name: str, col_name: str) -> list[str]:
    df = pd.read_excel(path, sheet_name=sheet_name, dtype=str)
    if col_name not in df.columns:
        raise ValueError(
            f"Column '{col_name}' not found in sheet '{sheet_name}'. "
            f"Available columns: {list(df.columns)}"
        )
    paths = df[col_name].str.strip().dropna()
    paths = paths[paths != ""].tolist()
    logger.info("Loaded %d blob paths from '%s'", len(paths), path)
    return paths


def copy_blobs(
    blob_paths: list[str],
    src_account_url: str,
    src_container: str,
    dst_account_url: str,
    dst_container: str,
    dest_folder: str,
    dry_run: bool,
) -> tuple[int, int]:
    credential = DefaultAzureCredential()
    src_client = BlobServiceClient(account_url=src_account_url, credential=credential)
    dst_client = (
        BlobServiceClient(account_url=dst_account_url, credential=credential)
        if dst_account_url != src_account_url
        else src_client
    )

    success, failure = 0, 0
    for blob_path in blob_paths:
        dst_name = f"{dest_folder}/{blob_path}"
        if dry_run:
            logger.info("[DRY RUN] Would copy: %s -> %s/%s", blob_path, dst_container, dst_name)
            success += 1
            continue
        try:
            src_blob = src_client.get_blob_client(container=src_container, blob=blob_path)
            dst_blob = dst_client.get_blob_client(container=dst_container, blob=dst_name)
            dst_blob.start_copy_from_url(src_blob.url)
            logger.info("Copied: %s -> %s/%s", blob_path, dst_container, dst_name)
            success += 1
        except Exception as exc:
            logger.warning("Failed to copy '%s': %s", blob_path, exc)
            failure += 1

    return success, failure


def run(args: argparse.Namespace) -> None:
    blob_paths = load_blob_paths(args.input_file, args.sheet_name, args.blob_path_col)
    dst_account_url = args.dest_account_url or args.account_url
    success, failure = copy_blobs(
        blob_paths=blob_paths,
        src_account_url=args.account_url,
        src_container=args.source_container,
        dst_account_url=dst_account_url,
        dst_container=args.dest_container,
        dest_folder=args.dest_folder,
        dry_run=args.dry_run,
    )
    logger.info("Done. %d copied, %d failed.", success, failure)
    if failure:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Copy blobs listed in an Excel file to a new folder in Azure Blob Storage."
    )
    parser.add_argument("input_file", help="Path to the input .xlsx file")
    parser.add_argument(
        "--account-url",
        required=True,
        help="Source storage account URL (e.g. https://<account>.blob.core.windows.net)",
    )
    parser.add_argument("--source-container", required=True, help="Source blob container name")
    parser.add_argument("--dest-container", required=True, help="Destination blob container name")
    parser.add_argument(
        "--dest-folder",
        required=True,
        help="Destination folder prefix (e.g. 'archive/2026')",
    )
    parser.add_argument(
        "--dest-account-url",
        default=None,
        help="Destination storage account URL for cross-account copies (defaults to --account-url)",
    )
    parser.add_argument(
        "--sheet-name",
        default=DEFAULT_SHEET_NAME,
        help=f"Sheet name in the Excel file (default: '{DEFAULT_SHEET_NAME}')",
    )
    parser.add_argument(
        "--blob-path-col",
        default=DEFAULT_BLOB_PATH_COL,
        help=f"Column name containing blob paths (default: '{DEFAULT_BLOB_PATH_COL}')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be copied without performing any copy operations",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        run(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
