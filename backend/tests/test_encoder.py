"""Tests for yoink.encoder."""

import base64
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from yoink.encoder import assemble_output, build_page_entry, encode_crop_to_base64, write_json
from yoink.mapper import Component


@pytest.fixture
def sample_crop():
    """A small 10x10 red image."""
    return np.full((10, 10, 3), (0, 0, 255), dtype=np.uint8)


@pytest.fixture
def sample_component(sample_crop):
    return Component(
        id=0,
        original_label="Picture",
        label_index=6,
        category="figure",
        confidence=0.95,
        bbox=[10, 20, 110, 120],
        crop=sample_crop,
    )


class TestEncodeBase64:
    def test_returns_string(self, sample_crop):
        result = encode_crop_to_base64(sample_crop)
        assert isinstance(result, str)

    def test_decodable(self, sample_crop):
        b64 = encode_crop_to_base64(sample_crop)
        decoded = base64.b64decode(b64)
        # Should be valid PNG bytes
        assert decoded[:4] == b"\x89PNG"


class TestBuildPageEntry:
    def test_structure(self, sample_component):
        entry = build_page_entry(1, [sample_component])
        assert entry["page_number"] == 1
        assert len(entry["components"]) == 1
        comp = entry["components"][0]
        assert comp["id"] == 0
        assert comp["category"] == "figure"
        assert comp["original_label"] == "Picture"
        assert isinstance(comp["base64"], str)
        assert comp["confidence"] == 0.95

    def test_empty_page(self):
        entry = build_page_entry(5, [])
        assert entry["page_number"] == 5
        assert entry["components"] == []


class TestAssembleOutput:
    def test_structure(self, sample_component):
        page = build_page_entry(1, [sample_component])
        output = assemble_output("test.pdf", [page])
        assert output["source_file"] == "test.pdf"
        assert output["total_pages"] == 1
        assert output["total_components"] == 1


class TestWriteJson:
    def test_writes_valid_json(self, tmp_path):
        data = {"key": "value", "nested": {"a": 1}}
        out = write_json(data, tmp_path / "out.json")
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert loaded == data

    def test_creates_parent_dirs(self, tmp_path):
        out_path = tmp_path / "deep" / "nested" / "output.json"
        write_json({"test": True}, out_path)
        assert out_path.exists()
