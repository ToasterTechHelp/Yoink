"""Base64Encoder: Convert cropped components to Base64 and assemble JSON output."""

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import cv2

from yoink.mapper import Component

logger = logging.getLogger(__name__)


def encode_crop_to_base64(crop, fmt: str = ".png") -> str:
    """Encode a BGR numpy array to a Base64 string."""
    success, buffer = cv2.imencode(fmt, crop)
    if not success:
        raise ValueError("Failed to encode crop to image buffer")
    return base64.b64encode(buffer).decode("utf-8")


def build_page_entry(page_number: int, components: List[Component]) -> Dict[str, Any]:
    """Build a single page's JSON entry."""
    return {
        "page_number": page_number,
        "components": [
            {
                **comp.model_dump(),
                "confidence": round(comp.confidence, 4),
                "base64": encode_crop_to_base64(comp.crop),
            }
            for comp in components
        ],
    }


def assemble_output(
    source_file: str,
    pages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assemble the final JSON output structure."""
    total_components = sum(len(p["components"]) for p in pages)
    return {
        "source_file": source_file,
        "total_pages": len(pages),
        "total_components": total_components,
        "pages": pages,
    }


def write_json(data: Dict[str, Any], output_path: str | Path) -> Path:
    """Write the assembled JSON to a file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info("Wrote output JSON: %s", output_path)
    return output_path
