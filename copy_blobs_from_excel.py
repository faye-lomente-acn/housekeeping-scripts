import argparse
import logging
import os
import sys

import pandas as pd
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

DEFAULT_SHEET_NAME = "license"
ACCOUNT_URL_ENV = "AZURE_STORAGE_ACCOUNT_URL"

logger = logging.getLogger(__name__)


def load_blob_records(path: str, sheet_name: str) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet_name, dtype=str)
    for col in ("InputBlobPath", "RowKey", "Filename"):
        if col not in df.columns:
            raise ValueError(
                f"Column '{col}' not found in sheet '{sheet_name}'. "
                f"Available columns: {list(df.columns)}"
            )
    df = df[["InputBlobPath", "RowKey", "Filename"]].dropna(how="any")
    df = df[df["InputBlobPath"].str.strip() != ""]
    logger.info("Loaded %d records from '%s'", len(df), path)
    return df.to_dict("records")


def derive_paths(
    record: dict,
    ocr_input_folder: str,
    extraction_output_folder: str,
    dest_folder: str,
) -> tuple[str, str]:
    input_blob_path = record["InputBlobPath"].strip().strip("/")
    prefix = ocr_input_folder.strip().strip("/")
    if not input_blob_path.startswith(prefix):
        raise ValueError(
            f"InputBlobPath '{input_blob_path}' does not start with "
            f"ocr-input-blob-folder '{prefix}'"
        )
    relative = input_blob_path[len(prefix):].strip("/")
    folder_name = relative.split("/")[0]

    blob_filename = f"{record['RowKey'].strip()}__{record['Filename'].strip()}"

    src = f"{extraction_output_folder.strip().strip('/')}/{folder_name}/{blob_filename}"
    dst = f"{dest_folder.strip().strip('/')}/{folder_name}/{blob_filename}"
    return src, dst


def copy_blobs(
    records: list[dict],
    ocr_input_folder: str,
    extraction_output_folder: str,
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
    for record in records:
        try:
            src_name, dst_name = derive_paths(
                record, ocr_input_folder, extraction_output_folder, dest_folder
            )
        except ValueError as exc:
            logger.warning("Skipping record %s: %s", record, exc)
            failure += 1
            continue

        if dry_run:
            logger.info(
                "[DRY RUN] Would copy: %s/%s -> %s/%s",
                src_container, src_name, dst_container, dst_name,
            )
            success += 1
            continue

        try:
            src_blob = src_client.get_blob_client(container=src_container, blob=src_name)
            dst_blob = dst_client.get_blob_client(container=dst_container, blob=dst_name)
            dst_blob.start_copy_from_url(src_blob.url)
            logger.info("Copied: %s/%s -> %s/%s", src_container, src_name, dst_container, dst_name)
            success += 1
        except Exception as exc:
            logger.warning("Failed to copy '%s': %s", src_name, exc)
            failure += 1

    return success, failure


def run(args: argparse.Namespace) -> None:
    account_url = os.environ.get(ACCOUNT_URL_ENV)
    if not account_url:
        raise ValueError(
            f"Environment variable '{ACCOUNT_URL_ENV}' is not set. "
            "Set it to the source storage account URL "
            "(e.g. https://<account>.blob.core.windows.net)."
        )
    records = load_blob_records(args.input_file, args.sheet_name)
    dst_account_url = args.dest_account_url or account_url
    success, failure = copy_blobs(
        records=records,
        ocr_input_folder=args.ocr_input_blob_folder,
        extraction_output_folder=args.extraction_output_blob_folder,
        src_account_url=account_url,
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
    parser.add_argument("--source-container", required=True, help="Source blob container name")
    parser.add_argument("--dest-container", required=True, help="Destination blob container name")
    parser.add_argument(
        "--dest-folder",
        required=True,
        help="Destination folder prefix (e.g. 'archive/2026')",
    )
    parser.add_argument(
        "--ocr-input-blob-folder",
        required=True,
        help="OCR input blob folder path used to extract the sub-folder name from InputBlobPath",
    )
    parser.add_argument(
        "--extraction-output-blob-folder",
        required=True,
        help="Extraction output blob folder path used as the source blob prefix",
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
