"""Test the official classifier label convention without loading model weights."""

import base64
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
from PIL import Image

from app.services.orientation_service import DocumentOrientationService


def _image_uri() -> str:
    image = Image.new("RGB", (6, 10), "white")
    image.putpixel((0, 0), (255, 0, 0))
    image.putpixel((5, 9), (0, 0, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


@pytest.mark.parametrize(
    ("label", "clockwise", "size", "red", "blue"),
    [(0, 0, (6, 10), (0, 0), (5, 9)),
     (90, 270, (10, 6), (0, 5), (9, 0)),
     (180, 180, (6, 10), (5, 9), (0, 0)),
     (270, 90, (10, 6), (9, 0), (0, 5))],
)
def test_classifier_angle_means_counterclockwise_correction_and_reports_applied_clockwise(
    tmp_path: Path, label: int, clockwise: int, size: tuple[int, int],
    red: tuple[int, int], blue: tuple[int, int],
) -> None:
    class Classifier:
        config = SimpleNamespace(id2label={0: str(label), 1: "other"})

        def __call__(self, **kwargs):
            assert kwargs == {"fixture": "original-image"}
            return SimpleNamespace(last_hidden_state=torch.tensor([[10.0, -10.0]]))

    def processor(*, images: Image.Image, return_tensors: str):
        assert images.size == (6, 10)
        assert images.getpixel((0, 0)) == (255, 0, 0)
        assert return_tensors == "pt"
        return {"fixture": "original-image"}

    orientation = DocumentOrientationService(tmp_path, allow_download=False)
    orientation._model = Classifier()
    orientation._processor = processor
    source_uri = _image_uri()

    uri, applied, confidence = orientation.orient(source_uri)

    assert applied == clockwise
    assert confidence > 0.999
    with Image.open(io.BytesIO(base64.b64decode(uri.partition(",")[2]))) as upright:
        assert upright.size == size
        assert upright.getpixel(red) == (255, 0, 0)
        assert upright.getpixel(blue) == (0, 0, 255)
    if label == 0:
        assert uri == source_uri
