"""
lambda_function.py
──────────────────
AWS Lambda handler for the Serverless Thumbnail Generator.

Triggered by S3 ObjectCreated events on the intake-bucket.
Supports: .jpg, .jpeg, .png  → resized thumbnail (max 200×200)
          .pdf               → page-1 rendered as PNG, then resized to max 200×200

Output thumbnails are prefixed with "thumb_" and uploaded to output-bucket.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from pathlib import Path
from typing import Optional

import boto3
from PIL import Image, UnidentifiedImageError

# pdf2image is a thin wrapper around Poppler's pdftoppm / pdftocairo.
from pdf2image import convert_from_path
from pdf2image.exceptions import (
    PDFInfoNotInstalledError,
    PDFPageCountError,
    PDFSyntaxError,
)

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
THUMBNAIL_MAX_SIZE: tuple[int, int] = (200, 200)
SUPPORTED_IMAGE_EXTS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png"})
SUPPORTED_PDF_EXTS: frozenset[str] = frozenset({".pdf"})
OUTPUT_BUCKET: str = os.environ.get("OUTPUT_BUCKET", "output-bucket")
TMP_DIR: str = "/tmp"  # Lambda's only writable directory


# ──────────────────────────────────────────────────────────────────────────────
# Helper: download from S3
# ──────────────────────────────────────────────────────────────────────────────
def _download_from_s3(s3_client, bucket: str, key: str, local_path: str) -> None:
    """Download an S3 object to a local file path."""
    logger.info("Downloading s3://%s/%s → %s", bucket, key, local_path)
    s3_client.download_file(bucket, key, local_path)


# ──────────────────────────────────────────────────────────────────────────────
# Helper: upload to S3
# ──────────────────────────────────────────────────────────────────────────────
def _upload_to_s3(s3_client, local_path: str, bucket: str, key: str) -> None:
    """Upload a local file to an S3 bucket."""
    logger.info("Uploading %s → s3://%s/%s", local_path, bucket, key)
    s3_client.upload_file(local_path, bucket, key)


# ──────────────────────────────────────────────────────────────────────────────
# Core processing: image thumbnail
# ──────────────────────────────────────────────────────────────────────────────
def create_image_thumbnail(input_path: str, output_path: str) -> None:
    """
    Open an image file, resize it proportionally to fit within THUMBNAIL_MAX_SIZE,
    and save it to output_path as PNG.

    Raises:
        UnidentifiedImageError: if Pillow cannot recognise the file format.
        OSError: on general I/O failures.
    """
    with Image.open(input_path) as img:
        # Convert palette-mode (P) or RGBA → RGB so JPEG-backend codecs are happy.
        # We always output PNG, so RGBA is fine to keep; only convert P.
        if img.mode == "P":
            img = img.convert("RGBA")

        img.thumbnail(THUMBNAIL_MAX_SIZE, Image.LANCZOS)
        img.save(output_path, format="PNG")
        logger.info(
            "Image thumbnail created: %s (size: %s)", output_path, img.size
        )


# ──────────────────────────────────────────────────────────────────────────────
# Core processing: PDF thumbnail
# ──────────────────────────────────────────────────────────────────────────────
def create_pdf_thumbnail(input_path: str, output_path: str) -> None:
    """
    Render page 1 of a PDF to a PIL Image using Poppler, resize it, and save
    it as a PNG thumbnail.

    Raises:
        PDFInfoNotInstalledError: if Poppler is not on the system PATH.
        PDFPageCountError: if the PDF has no pages.
        PDFSyntaxError: if the PDF is corrupt/malformed.
        OSError: on general I/O failures.
    """
    # convert_from_path returns a list of PIL Images, one per page.
    # first_page=1, last_page=1 limits conversion to page 1 for performance.
    pages = convert_from_path(
        input_path,
        dpi=150,
        first_page=1,
        last_page=1,
        output_folder=TMP_DIR,
        fmt="png",
    )

    if not pages:
        raise ValueError(f"No pages could be rendered from PDF: {input_path}")

    page_image: Image.Image = pages[0]
    page_image.thumbnail(THUMBNAIL_MAX_SIZE, Image.LANCZOS)
    page_image.save(output_path, format="PNG")
    logger.info(
        "PDF thumbnail created: %s (size: %s)", output_path, page_image.size
    )


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrator: decide processing path based on file extension
# ──────────────────────────────────────────────────────────────────────────────
def process_file(input_path: str, output_path: str, extension: str) -> None:
    """
    Route the file to the appropriate thumbnail-creation function.

    Args:
        input_path:  Local path to the downloaded source file.
        output_path: Local path where the thumbnail should be written.
        extension:   Lowercased file extension including leading dot, e.g. '.pdf'.

    Raises:
        ValueError: for unsupported file types.
    """
    if extension in SUPPORTED_IMAGE_EXTS:
        create_image_thumbnail(input_path, output_path)
    elif extension in SUPPORTED_PDF_EXTS:
        create_pdf_thumbnail(input_path, output_path)
    else:
        raise ValueError(
            f"Unsupported file extension '{extension}'. "
            f"Supported: {SUPPORTED_IMAGE_EXTS | SUPPORTED_PDF_EXTS}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Lambda entry point
# ──────────────────────────────────────────────────────────────────────────────
def handler(event: dict, context) -> dict:
    """
    AWS Lambda handler.

    Processes all S3 records contained in the incoming event.  Each record
    represents one newly-created object in the intake-bucket.

    Returns a summary dict with per-key success/failure information.
    """
    s3_client = boto3.client("s3")
    results: list[dict] = []

    records = event.get("Records", [])
    if not records:
        logger.warning("Event contained no Records — nothing to process.")
        return {"processed": 0, "results": results}

    for record in records:
        source_bucket: str = record["s3"]["bucket"]["name"]
        # Keys with special characters are URL-encoded by S3 notifications.
        object_key: str = urllib.parse.unquote_plus(
            record["s3"]["object"]["key"]
        )

        logger.info("Processing: s3://%s/%s", source_bucket, object_key)

        # Build local file paths inside /tmp (Lambda's writable scratch space).
        source_filename: str = Path(object_key).name
        extension: str = Path(source_filename).suffix.lower()
        local_input: str = os.path.join(TMP_DIR, source_filename)

        thumb_filename: str = f"thumb_{Path(source_filename).stem}.png"
        local_output: str = os.path.join(TMP_DIR, thumb_filename)
        # Mirror the original key's directory structure in the output bucket.
        output_key: str = str(
            Path(object_key).parent / thumb_filename
        ).replace("\\", "/")

        try:
            # 1. Download source file from intake-bucket.
            _download_from_s3(s3_client, source_bucket, object_key, local_input)

            # 2. Generate thumbnail.
            process_file(local_input, local_output, extension)

            # 3. Upload thumbnail to output-bucket.
            _upload_to_s3(s3_client, local_output, OUTPUT_BUCKET, output_key)

            results.append({"key": object_key, "status": "success", "output": output_key})
            logger.info("SUCCESS: %s → s3://%s/%s", object_key, OUTPUT_BUCKET, output_key)

        except ValueError as exc:
            # Unsupported format — log and continue without crashing.
            logger.error("SKIPPED [unsupported format]: %s — %s", object_key, exc)
            results.append({"key": object_key, "status": "skipped", "reason": str(exc)})

        except (UnidentifiedImageError, PDFSyntaxError, PDFPageCountError) as exc:
            # Corrupt or unreadable file — log and continue.
            logger.error("SKIPPED [corrupt file]: %s — %s", object_key, exc)
            results.append({"key": object_key, "status": "skipped", "reason": str(exc)})

        except PDFInfoNotInstalledError as exc:
            # Poppler missing — this is a deployment/environment error; raise to signal Lambda failure.
            logger.critical("Poppler not installed — cannot process PDFs: %s", exc)
            raise

        except Exception as exc:
            # Unexpected errors — log with full traceback and continue.
            logger.exception("ERROR processing %s: %s", object_key, exc)
            results.append({"key": object_key, "status": "error", "reason": str(exc)})

        finally:
            # Always clean up /tmp to avoid storage exhaustion across warm invocations.
            for path in (local_input, local_output):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                        logger.debug("Cleaned up temp file: %s", path)
                except OSError as cleanup_err:
                    logger.warning("Could not clean up %s: %s", path, cleanup_err)

    return {"processed": len(results), "results": results}
