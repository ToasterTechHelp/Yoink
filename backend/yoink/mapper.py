"""ComponentMapper: Categorize detections and crop regions from source images."""

import logging
from enum import Enum
from typing import Dict, List, Literal

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from yoink.extractor import Detection

logger = logging.getLogger(__name__)

# Label index → category mapping (from YOLO model)
# Model classes: title, plain text, abandon, figure, figure_caption,
#                table, table_caption, table_footnote, isolate_formula, formula_caption
CATEGORY_MAP: Dict[int, str] = {
    0: "text",  # title
    1: "text",  # plain text
    2: "misc",  # abandon (headers/footers)
    3: "figure",  # figure
    4: "misc",  # figure_caption
    5: "figure",  # table
    6: "misc",  # table_caption
    7: "misc",  # table_footnote
    8: "text",  # isolate_formula
    9: "misc",  # formula_caption
}


class Component(BaseModel):
    """A cropped and categorized document component."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int
    original_label: str
    label_index: int = Field(ge=0, le=9)
    category: Literal["text", "figure", "misc"]
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: List[int] = Field(min_length=4, max_length=4)
    crop: np.ndarray = Field(exclude=True)  # BGR image array, excluded from serialization


def _load_image(image_path: str) -> np.ndarray:
    """Load an image from disk, raising ValueError if it fails."""
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Failed to read image: {image_path}")
    return image


def _crop_detection(
    image: np.ndarray,
    det: Detection,
    index: int,
) -> np.ndarray | None:
    """Crop a detection from the image, clamping to bounds. Returns None if empty."""
    x1, y1, x2, y2 = det.bbox
    h, w = image.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)

    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        logger.warning("Empty crop for detection %d (%s), skipping", index, det.label)
        return None
    return crop


def _build_component(
    det: Detection,
    crop: np.ndarray,
    component_id: int,
) -> Component:
    """Build a Component from a detection and its crop."""
    category = CATEGORY_MAP.get(det.label_index, "text")
    return Component(
        id=component_id,
        original_label=det.label,
        label_index=det.label_index,
        category=category,
        confidence=det.confidence,
        bbox=det.bbox,
        crop=crop,
    )


def map_and_crop(
    detections: List[Detection],
    image_path: str,
    component_id_start: int = 0,
) -> List[Component]:
    """
    Map detections to categories and crop regions from the source image.

    Args:
        detections: List of Detection objects from the extractor.
        image_path: Path to the source image to crop from.
        component_id_start: Starting ID for components (for global uniqueness).

    Returns:
        List of Component objects with cropped image data.
    """
    image = _load_image(image_path)

    components: List[Component] = []
    for i, det in enumerate(detections):
        crop = _crop_detection(image, det, i)
        if crop is None:
            continue

        components.append(_build_component(det, crop, component_id_start + i))

    logger.info(
        "Mapped %d detections → %d components (text: %d, figure: %d, misc: %d)",
        len(detections),
        len(components),
        sum(1 for c in components if c.category == "text"),
        sum(1 for c in components if c.category == "figure"),
        sum(1 for c in components if c.category == "misc"),
    )
    return components
