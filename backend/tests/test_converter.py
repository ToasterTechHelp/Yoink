"""Tests for yoink.converter."""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from yoink.converter import ConversionError, convert_file, detect_file_type


class TestDetectFileType:
    def test_png(self):
        assert detect_file_type(Path("test.png")) == "image"

    def test_jpg(self):
        assert detect_file_type(Path("test.jpg")) == "image"

    def test_jpeg(self):
        assert detect_file_type(Path("test.jpeg")) == "image"

    def test_pdf(self):
        assert detect_file_type(Path("test.pdf")) == "pdf"

    def test_unsupported(self):
        with pytest.raises(ConversionError, match="Unsupported file type"):
            detect_file_type(Path("test.pptx"))

    def test_no_extension(self):
        with pytest.raises(ConversionError):
            detect_file_type(Path("noextension"))


class TestConvertFile:
    def test_image_to_png(self, tmp_path):
        # Create a small test image
        img_path = tmp_path / "test.jpg"
        Image.new("RGB", (100, 80), color="red").save(img_path)

        out_dir = tmp_path / "out"
        pages = convert_file(img_path, output_dir=out_dir)

        assert len(pages) == 1
        assert pages[0][0] == 1  # page number
        assert pages[0][1].exists()
        assert pages[0][1].suffix == ".png"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            convert_file("/nonexistent/file.png")

    def test_unsupported_format(self, tmp_path):
        bad_file = tmp_path / "test.pptx"
        bad_file.write_text("not a real pptx")
        with pytest.raises(ConversionError):
            convert_file(bad_file)

    def test_corrupt_image(self, tmp_path):
        corrupt = tmp_path / "corrupt.png"
        corrupt.write_bytes(b"not an image")
        with pytest.raises(ConversionError, match="Invalid image"):
            convert_file(corrupt, output_dir=tmp_path / "out")

    def test_pdf_conversion(self, tmp_path):
        """Basic PDF test — creates a minimal 1-page PDF with PyMuPDF."""
        import fitz

        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page(width=200, height=200)
        page.insert_text((50, 100), "Hello Yoink!")
        doc.save(str(pdf_path))
        doc.close()

        out_dir = tmp_path / "out"
        pages = convert_file(pdf_path, output_dir=out_dir)

        assert len(pages) == 1
        assert pages[0][0] == 1
        assert pages[0][1].exists()

    def test_multi_page_pdf(self, tmp_path):
        import fitz

        pdf_path = tmp_path / "multi.pdf"
        doc = fitz.open()
        for i in range(5):
            page = doc.new_page(width=200, height=200)
            page.insert_text((50, 100), f"Page {i+1}")
        doc.save(str(pdf_path))
        doc.close()

        pages = convert_file(pdf_path, output_dir=tmp_path / "out")
        assert len(pages) == 5
        assert [p[0] for p in pages] == [1, 2, 3, 4, 5]
