"""
tests/test_local.py
───────────────────
Offline test suite for the thumbnail generator core processing logic.

Runs WITHOUT any live AWS services.  Uses synthetic in-memory images and
a minimal fake PDF so the tests work even if Poppler is not installed on
the dev machine (the PDF test is skipped automatically in that case).

Run from the project root:
    pip install Pillow pdf2image pytest
    pytest tests/test_local.py -v
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure src/ is on the path when running tests directly (without install).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import Image
import pytest

# ── Import the functions under test ──────────────────────────────────────────
from lambda_function import (
    THUMBNAIL_MAX_SIZE,
    create_image_thumbnail,
    process_file,
)

# Try importing PDF utilities; skip PDF tests gracefully if Poppler is absent.
try:
    from lambda_function import create_pdf_thumbnail
    from pdf2image.exceptions import PDFInfoNotInstalledError

    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_test_image(
    width: int = 800,
    height: int = 600,
    color: str = "blue",
    fmt: str = "PNG",
    mode: str = "RGB",
) -> bytes:
    """Return the raw bytes of a synthetic PIL image."""
    img = Image.new(mode, (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _make_test_jpeg(width: int = 1024, height: int = 768) -> bytes:
    """Return bytes of a synthetic JPEG image."""
    img = Image.new("RGB", (width, height), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_minimal_pdf() -> bytes:
    """
    Return the bytes of a minimal but valid single-page PDF.
    This is a hand-crafted PDF containing a white 200×200 pt page with a
    single text string.  It passes Poppler's parser without errors.
    """
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj

2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj

3 0 obj
<< /Type /Page /Parent 2 0 R
   /MediaBox [0 0 200 200]
   /Contents 4 0 R
   /Resources << /Font << /F1 5 0 R >> >> >>
endobj

4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 50 100 Td (Test Page) Tj ET
endstream
endobj

5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj

xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000062 00000 n 
0000000119 00000 n 
0000000274 00000 n 
0000000370 00000 n 

trailer
<< /Size 6 /Root 1 0 R >>
startxref
452
%%EOF"""
    return pdf_content


# ──────────────────────────────────────────────────────────────────────────────
# Test class
# ──────────────────────────────────────────────────────────────────────────────

class TestImageThumbnail(unittest.TestCase):
    """Tests for image → thumbnail conversion."""

    def _assert_thumbnail_valid(self, output_path: str) -> Image.Image:
        """Load the thumbnail, assert it exists and fits within the max size."""
        self.assertTrue(os.path.exists(output_path), f"Thumbnail not created at {output_path}")
        with Image.open(output_path) as img:
            w, h = img.size
            self.assertLessEqual(w, THUMBNAIL_MAX_SIZE[0], f"Width {w} exceeds max {THUMBNAIL_MAX_SIZE[0]}")
            self.assertLessEqual(h, THUMBNAIL_MAX_SIZE[1], f"Height {h} exceeds max {THUMBNAIL_MAX_SIZE[1]}")
            return img.copy()

    # ── PNG tests ──────────────────────────────────────────────────────────

    def test_png_large_landscape_is_resized(self):
        """A large landscape PNG must be scaled down to ≤ 200×200."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "large.png")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_test_image(800, 400))

            create_image_thumbnail(src, dst)
            thumb = self._assert_thumbnail_valid(dst)
            # Aspect ratio check: original is 2:1, so thumb should be 200×100.
            self.assertEqual(thumb.size, (200, 100))

    def test_png_large_portrait_is_resized(self):
        """A tall portrait PNG must be scaled to ≤ 200×200 preserving ratio."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "portrait.png")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_test_image(400, 800))

            create_image_thumbnail(src, dst)
            thumb = self._assert_thumbnail_valid(dst)
            self.assertEqual(thumb.size, (100, 200))

    def test_png_already_small_stays_same(self):
        """An image already smaller than 200×200 must not be upscaled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "small.png")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_test_image(50, 30))

            create_image_thumbnail(src, dst)
            thumb = self._assert_thumbnail_valid(dst)
            self.assertEqual(thumb.size, (50, 30), "Small image must not be upscaled.")

    def test_png_square_is_resized_correctly(self):
        """A square PNG should become exactly 200×200."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "square.png")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_test_image(600, 600))

            create_image_thumbnail(src, dst)
            thumb = self._assert_thumbnail_valid(dst)
            self.assertEqual(thumb.size, (200, 200))

    def test_png_rgba_mode_handled(self):
        """A PNG with alpha channel (RGBA) must be handled without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "rgba.png")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_test_image(400, 400, mode="RGBA"))

            create_image_thumbnail(src, dst)
            self._assert_thumbnail_valid(dst)

    def test_png_palette_mode_handled(self):
        """A palette-mode (P) PNG must convert without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "palette.png")
            dst = os.path.join(tmpdir, "thumb.png")
            img = Image.new("P", (400, 400))
            img.save(src, format="PNG")

            create_image_thumbnail(src, dst)
            self._assert_thumbnail_valid(dst)

    # ── JPEG tests ─────────────────────────────────────────────────────────

    def test_jpeg_is_resized(self):
        """A large JPEG should be thumbnailed to ≤ 200×200."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "photo.jpg")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_test_jpeg(1024, 768))

            create_image_thumbnail(src, dst)
            self._assert_thumbnail_valid(dst)

    def test_output_is_always_png(self):
        """Thumbnail output must be saved as PNG regardless of input format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "photo.jpg")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_test_jpeg())

            create_image_thumbnail(src, dst)
            with Image.open(dst) as img:
                self.assertEqual(img.format, "PNG")

    # ── Error handling ─────────────────────────────────────────────────────

    def test_corrupt_image_raises_error(self):
        """Feeding random bytes should raise an UnidentifiedImageError."""
        from PIL import UnidentifiedImageError

        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "corrupt.png")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(b"\x00\x01\x02corrupt_data_not_a_real_image\xff\xfe")

            with self.assertRaises(UnidentifiedImageError):
                create_image_thumbnail(src, dst)

    def test_unsupported_extension_raises_value_error(self):
        """process_file must raise ValueError for unsupported extensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "file.bmp")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_test_image())  # valid PNG bytes but wrong ext

            with self.assertRaises(ValueError, msg="Expected ValueError for .bmp"):
                process_file(src, dst, ".bmp")


# ──────────────────────────────────────────────────────────────────────────────
# PDF tests (skipped if Poppler / pdf2image unavailable)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not PDF_AVAILABLE, reason="pdf2image / Poppler not available")
class TestPdfThumbnail(unittest.TestCase):
    """Tests for PDF → thumbnail conversion (requires Poppler on PATH)."""

    def test_pdf_page1_is_rendered_and_resized(self):
        """A valid single-page PDF must produce a thumbnail ≤ 200×200."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "doc.pdf")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_minimal_pdf())

            try:
                create_pdf_thumbnail(src, dst)
            except PDFInfoNotInstalledError:
                self.skipTest("Poppler not installed on this machine.")

            self.assertTrue(os.path.exists(dst))
            with Image.open(dst) as img:
                w, h = img.size
                self.assertLessEqual(w, 200)
                self.assertLessEqual(h, 200)

    def test_pdf_via_process_file(self):
        """process_file('.pdf') must route correctly and produce a thumbnail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "doc.pdf")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_minimal_pdf())

            try:
                process_file(src, dst, ".pdf")
            except PDFInfoNotInstalledError:
                self.skipTest("Poppler not installed on this machine.")

            self.assertTrue(os.path.exists(dst))


# ──────────────────────────────────────────────────────────────────────────────
# process_file routing tests
# ──────────────────────────────────────────────────────────────────────────────

class TestProcessFileRouting(unittest.TestCase):
    """Verify process_file routes correctly for all supported extensions."""

    def test_routes_jpg(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "img.jpg")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_test_jpeg())
            process_file(src, dst, ".jpg")
            self.assertTrue(os.path.exists(dst))

    def test_routes_jpeg(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "img.jpeg")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_test_jpeg())
            process_file(src, dst, ".jpeg")
            self.assertTrue(os.path.exists(dst))

    def test_routes_png(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "img.png")
            dst = os.path.join(tmpdir, "thumb.png")
            with open(src, "wb") as f:
                f.write(_make_test_image())
            process_file(src, dst, ".png")
            self.assertTrue(os.path.exists(dst))

    def test_rejects_gif(self):
        with self.assertRaises(ValueError):
            process_file("dummy.gif", "out.png", ".gif")

    def test_rejects_tiff(self):
        with self.assertRaises(ValueError):
            process_file("dummy.tiff", "out.png", ".tiff")

    def test_rejects_empty_extension(self):
        with self.assertRaises(ValueError):
            process_file("dummy", "out.png", "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
