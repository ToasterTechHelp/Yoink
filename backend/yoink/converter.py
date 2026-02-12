"""FileConverter: Convert PDF and image files to a list of PNG images (one per page)."""

import logging
import tempfile
from pathlib import Path
from typing import List, Tuple

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
SUPPORTED_PDF_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_PDF_EXTENSIONS


class ConversionError(Exception):
    """Raised when file conversion fails."""


def detect_file_type(file_path: Path) -> str:
    """Return 'image', 'pdf', or raise ConversionError for unsupported types."""
    ext = file_path.suffix.lower()
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        return "image"
    if ext in SUPPORTED_PDF_EXTENSIONS:
        return "pdf"
    raise ConversionError(
        f"Unsupported file type: '{ext}'. "
        f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
    )


def convert_image(file_path: Path, output_dir: Path) -> List[Tuple[int, Path]]:
    """Validate and convert a single image file to PNG. Returns [(1, png_path)]."""
    try:
        img = Image.open(file_path)
        img.verify()
        # Re-open after verify (verify closes the file)
        img = Image.open(file_path)
    except Exception as e:
        raise ConversionError(f"Invalid image file '{file_path}': {e}") from e

    png_path = output_dir / f"page_1.png"
    img.convert("RGB").save(png_path, "PNG")
    logger.info("Converted image to PNG: %s", png_path)
    return [(1, png_path)]


def convert_pdf(file_path: Path, output_dir: Path, dpi: int = 200) -> List[Tuple[int, Path]]:
    """Render each page of a PDF to PNG. Returns [(page_number, png_path), ...]."""
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise ConversionError(f"Failed to open PDF '{file_path}': {e}") from e

    pages: List[Tuple[int, Path]] = []
    zoom = dpi / 72  # PyMuPDF default is 72 DPI
    matrix = fitz.Matrix(zoom, zoom)

    max_pages = min(len(doc), 100)
    for page_num in range(max_pages):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=matrix)
        png_path = output_dir / f"page_{page_num + 1}.png"
        pix.save(str(png_path))
        pages.append((page_num + 1, png_path))
        logger.info("Rendered PDF page %d/%d", page_num + 1, len(doc))

    doc.close()
    return pages


def convert_file(file_path: str | Path, output_dir: str | Path | None = None, dpi: int = 200) -> List[Tuple[int, Path]]:
    """
    Convert a PDF or image file to a list of PNG images.

    Args:
        file_path: Path to the input file.
        output_dir: Directory to write PNGs into. If None, uses a temp directory.
        dpi: Resolution for PDF rendering (default 200).

    Returns:
        List of (page_number, png_path) tuples.

    Raises:
        ConversionError: If the file type is unsupported or conversion fails.
        FileNotFoundError: If the input file doesn't exist.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: '{file_path}'")

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="yoink_"))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    file_type = detect_file_type(file_path)

    if file_type == "image":
        return convert_image(file_path, output_dir)
    elif file_type == "pdf":
        return convert_pdf(file_path, output_dir, dpi=dpi)
    else:
        raise ConversionError(f"Unhandled file type: {file_type}")
