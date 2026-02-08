"""Pipeline: Orchestrates the full extraction flow (Converter → Extractor → Mapper → Encoder)."""

import logging
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from yoink.converter import convert_file
from yoink.encoder import assemble_output, build_page_entry, write_json
from yoink.extractor import LayoutExtractor
from yoink.mapper import map_and_crop

logger = logging.getLogger(__name__)


def run_pipeline(
    input_file: str | Path,
    output_dir: str | Path = "./output",
    extractor: Optional[LayoutExtractor] = None,
    model_path: Optional[str] = None,
    imgsz: int = 1024,
    conf: float = 0.2,
    device: Optional[str] = None,
    dpi: int = 200,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, Any]:
    """
    Run the full extraction pipeline on an input file.

    This is the primary programmatic entry point. The CLI and API
    endpoint both call this function.

    Args:
        input_file: Path to a PDF or image file.
        output_dir: Directory to write the output JSON into.
        extractor: Pre-loaded LayoutExtractor instance. If None, creates one.
        model_path: Path to YOLO .pt weights (only used if extractor is None).
        imgsz: YOLO prediction image size (only used if extractor is None).
        conf: YOLO confidence threshold (only used if extractor is None).
        device: Device string (only used if extractor is None).
        dpi: PDF rendering resolution.
        progress_callback: Called with (current_page, total_pages) after each page.

    Returns:
        The assembled output dict (same structure as the JSON file).
    """
    input_file = Path(input_file)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting pipeline for: %s", input_file)

    # Step 1: Convert file to page images
    with tempfile.TemporaryDirectory(prefix="yoink_pages_") as tmp_dir:
        pages = convert_file(input_file, output_dir=tmp_dir, dpi=dpi)
        logger.info("Converted %d page(s)", len(pages))

        # Step 2: Use provided extractor or create one
        if extractor is None:
            extractor = LayoutExtractor(
                model_path=model_path,
                imgsz=imgsz,
                conf=conf,
                device=device,
            )

        # Step 3–4: Extract, map, and encode page-by-page
        page_entries = []
        component_id = 0

        for page_number, page_path in pages:
            logger.info("Processing page %d/%d...", page_number, len(pages))

            # Extract layout
            result = extractor.extract(page_path)

            # Map to categories and crop
            components = map_and_crop(
                detections=result.detections,
                image_path=result.image_path,
                component_id_start=component_id,
            )
            component_id += len(components)

            # Build page JSON entry (encodes crops to base64)
            page_entry = build_page_entry(page_number, components)
            page_entries.append(page_entry)

            if progress_callback is not None:
                progress_callback(page_number, len(pages))

        # Step 5: Assemble and write JSON
        output_data = assemble_output(
            source_file=input_file.name,
            pages=page_entries,
        )

        output_filename = input_file.stem + "_extracted.json"
        output_path = output_dir / output_filename
        write_json(output_data, output_path)

    logger.info(
        "Pipeline complete: %d pages, %d components → %s",
        output_data["total_pages"],
        output_data["total_components"],
        output_path,
    )
    return output_data
