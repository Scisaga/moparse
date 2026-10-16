"""Official PP-LCNet document orientation on CPU before scan-page recognition."""

from __future__ import annotations

import base64
import io
import threading
from pathlib import Path
from typing import Any

from PIL import Image

MODEL_REPOSITORY = "PaddlePaddle/PP-LCNet_x1_0_doc_ori_safetensors"
MODEL_REVISION = "b2716954d2e321dd4436400b37584fab641027ab"


class DocumentOrientationService:
    """Use the official classifier and its processor without text heuristics.

    The classifier labels the counterclockwise correction angle. Callers receive
    the clockwise rotation actually applied, for mapping SDK coordinates back to
    the rendered source page. PDF's own rotation is already handled by rendering.
    """

    def __init__(self, model_path: Path, *, allow_download: bool = True) -> None:
        self.model_path = model_path
        self.allow_download = allow_download
        self._lock = threading.Lock()
        self._processor: Any = None
        self._model: Any = None

    def initialize(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            from transformers import AutoImageProcessor, AutoModelForImageClassification

            if not (self.model_path / "model.safetensors").is_file():
                if not self.allow_download:
                    raise FileNotFoundError(f"Orientation model is missing: {self.model_path}")
                from huggingface_hub import snapshot_download

                snapshot_download(
                    repo_id=MODEL_REPOSITORY,
                    revision=MODEL_REVISION,
                    local_dir=self.model_path,
                    allow_patterns=["*.json", "model.safetensors"],
                )
            processor = AutoImageProcessor.from_pretrained(self.model_path, local_files_only=True)
            model = (
                AutoModelForImageClassification.from_pretrained(
                    self.model_path, local_files_only=True
                )
                .to("cpu")
                .eval()
            )
            self._processor = processor
            self._model = model

    def orient(self, image_uri: str) -> tuple[str, int, float]:
        """Return the upright image URI, applied clockwise angle and confidence."""
        self.initialize()
        import torch

        header, separator, encoded = image_uri.partition(",")
        if not separator or not header.startswith("data:image/") or ";base64" not in header:
            raise ValueError("Orientation requires a base64 image URI")
        payload = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(payload)) as source:
            image = source.convert("RGB")
        with self._lock, torch.inference_mode():
            inputs = self._processor(images=image, return_tensors="pt")
            # The official PP-LCNet classifier exposes its classification head
            # as last_hidden_state (rather than the generic ImageClassifierOutput).
            logits = self._model(**inputs).last_hidden_state
            probabilities = logits.float().softmax(dim=-1)[0]
            index = int(probabilities.argmax().item())
            angle = int(self._model.config.id2label[index])
            confidence = float(probabilities[index].item())
        if angle not in {0, 90, 180, 270}:
            raise ValueError("Orientation model returned an invalid correction angle")
        if angle == 0:
            return image_uri, 0, confidence
        upright = image.rotate(angle, expand=True)
        output = io.BytesIO()
        upright.save(output, format="PNG")
        uri = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
        return uri, (-angle) % 360, confidence
