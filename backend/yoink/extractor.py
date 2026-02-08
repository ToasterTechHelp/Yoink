"""LayoutExtractor: Run DocLayout-YOLO inference on images."""

import logging
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from doclayout_yolo import YOLOv10
from huggingface_hub import hf_hub_download

logger = logging.getLogger(__name__)

DEFAULT_REPO_ID = "juliozhao/DocLayout-YOLO-DocStructBench"
DEFAULT_MODEL_FILENAME = "doclayout_yolo_docstructbench_imgsz1024.pt"


class Detection(BaseModel):
    """A single detected document component."""
    label: str
    label_index: int = Field(ge=0, le=10)
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: List[int] = Field(min_length=4, max_length=4)


class ExtractionResult(BaseModel):
    """All detections for a single image."""
    image_path: str
    detections: List[Detection] = Field(default_factory=list)


class LayoutExtractor:
    """Wraps DocLayout-YOLO for document layout detection."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        imgsz: int = 1024,
        conf: float = 0.2,
        device: Optional[str] = None,
    ):
        """
        Args:
            model_path: Path to .pt weights. If None, downloads from HuggingFace.
            imgsz: Prediction image size.
            conf: Confidence threshold.
            device: Device string (e.g. 'cpu', 'cuda:0'). None = auto.
        """
        self.imgsz = imgsz
        self.conf = conf
        self.device = device

        if model_path is None:
            logger.info("Downloading model from HuggingFace...")
            model_path = hf_hub_download(
                repo_id=DEFAULT_REPO_ID,
                filename=DEFAULT_MODEL_FILENAME,
            )
        self._model = YOLOv10(model_path)
        logger.info("Model loaded: %s", model_path)

    def extract(self, image_path: str | Path) -> ExtractionResult:
        """
        Run layout detection on a single image.

        Args:
            image_path: Path to the PNG image.

        Returns:
            ExtractionResult with all detections.
        """
        image_path = str(image_path)
        predict_kwargs = {
            "imgsz": self.imgsz,
            "conf": self.conf,
        }
        if self.device is not None:
            predict_kwargs["device"] = self.device

        results = self._model.predict(image_path, **predict_kwargs)
        result = results[0]

        detections: List[Detection] = []
        for box in result.boxes:
            label_idx = int(box.cls[0])
            detections.append(
                Detection(
                    label=result.names[label_idx],
                    label_index=label_idx,
                    confidence=float(box.conf[0]),
                    bbox=list(map(int, box.xyxy[0])),
                )
            )

        logger.info("Found %d components in %s", len(detections), image_path)
        return ExtractionResult(image_path=image_path, detections=detections)
