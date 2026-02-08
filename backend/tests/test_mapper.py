"""Tests for yoink.mapper."""

import numpy as np
import pytest

from yoink.extractor import Detection
from yoink.mapper import CATEGORY_MAP, Component, map_and_crop


@pytest.fixture
def sample_image(tmp_path):
    """Create a simple 200x300 test image and return its path."""
    import cv2

    img = np.zeros((200, 300, 3), dtype=np.uint8)
    img[50:150, 50:250] = (0, 255, 0)  # green rectangle
    path = str(tmp_path / "test.png")
    cv2.imwrite(path, img)
    return path


class TestCategoryMap:
    def test_all_labels_covered(self):
        """Ensure all 10 model labels (0–9) have a mapping."""
        for i in range(10):
            assert i in CATEGORY_MAP

    def test_figure_is_figure(self):
        assert CATEGORY_MAP[3] == "figure"

    def test_table_is_figure(self):
        assert CATEGORY_MAP[5] == "figure"

    def test_text_labels(self):
        text_indices = [0, 1, 8]  # title, plain text, isolate_formula
        for idx in text_indices:
            assert CATEGORY_MAP[idx] == "text"

    def test_misc_labels(self):
        misc_indices = [2, 4, 6, 7, 9]  # abandon, figure_caption, table_caption, table_footnote, formula_caption
        for idx in misc_indices:
            assert CATEGORY_MAP[idx] == "misc"


class TestMapAndCrop:
    def test_basic_crop(self, sample_image):
        detections = [
            Detection(label="figure", label_index=3, confidence=0.9, bbox=[50, 50, 250, 150]),
        ]
        components = map_and_crop(detections, sample_image)

        assert len(components) == 1
        assert components[0].category == "figure"
        assert components[0].original_label == "figure"
        assert components[0].crop.shape == (100, 200, 3)

    def test_multiple_detections(self, sample_image):
        detections = [
            Detection(label="plain text", label_index=1, confidence=0.8, bbox=[0, 0, 100, 50]),
            Detection(label="table", label_index=5, confidence=0.7, bbox=[100, 100, 200, 200]),
        ]
        components = map_and_crop(detections, sample_image)
        assert len(components) == 2
        assert components[0].category == "text"
        assert components[1].category == "figure"

    def test_bbox_clamped_to_image_bounds(self, sample_image):
        detections = [
            Detection(label="plain text", label_index=1, confidence=0.9, bbox=[-10, -10, 310, 210]),
        ]
        components = map_and_crop(detections, sample_image)
        assert len(components) == 1
        # Should be clamped to image size (300x200)
        assert components[0].crop.shape == (200, 300, 3)

    def test_empty_crop_skipped(self, sample_image):
        detections = [
            Detection(label="plain text", label_index=1, confidence=0.9, bbox=[0, 0, 0, 0]),
        ]
        components = map_and_crop(detections, sample_image)
        assert len(components) == 0

    def test_component_ids(self, sample_image):
        detections = [
            Detection(label="plain text", label_index=1, confidence=0.8, bbox=[0, 0, 50, 50]),
            Detection(label="title", label_index=0, confidence=0.9, bbox=[50, 50, 100, 100]),
        ]
        components = map_and_crop(detections, sample_image, component_id_start=10)
        assert components[0].id == 10
        assert components[1].id == 11

    def test_invalid_image_path(self):
        with pytest.raises(ValueError, match="Failed to read image"):
            map_and_crop(
                [Detection(label="plain text", label_index=1, confidence=0.9, bbox=[0, 0, 10, 10])],
                "/nonexistent.png",
            )
