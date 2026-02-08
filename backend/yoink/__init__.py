"""Yoink! — Extract components from lecture notes using AI-powered document layout detection."""

__version__ = "0.1.0"

from yoink.pipeline import run_pipeline
from yoink.extractor import LayoutExtractor, Detection, ExtractionResult
from yoink.mapper import Component, map_and_crop, CATEGORY_MAP

__all__ = [
    "run_pipeline",
    "LayoutExtractor",
    "Detection",
    "ExtractionResult",
    "Component",
    "map_and_crop",
    "CATEGORY_MAP",
]
