"""Pinned research-only PaddleX region transport and generation observations.

Layout continues to receive BGR arrays. Only the native Transformers region
boundary converts a BGR ndarray into a PIL RGB image. No answers are edited.
Token inspection and metadata serialization belong after the processing clock.
"""

from __future__ import annotations

import contextvars
import functools
import importlib.metadata
from collections.abc import Mapping
from typing import Any

SUPPORTED_VERSIONS = {"paddleocr": "3.7.0", "paddlex": "3.7.2", "transformers": "5.10.2"}
MAX_NEW_TOKENS = 4096
_CURRENT: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "moparse_paddle_region_generation", default=None
)


def region_bgr_to_pil(image: Any) -> Any:
    """Convert SDK region arrays once; let upstream fetch_image handle PIL/path."""
    import numpy as np
    from PIL import Image

    if not isinstance(image, np.ndarray):
        return image
    if image.ndim == 2:
        return Image.fromarray(image).convert("RGB")
    if image.ndim != 3 or image.shape[-1] not in {3, 4}:
        raise ValueError("Paddle native region must be HxW, HxWx3 BGR or HxWx4 BGRA")
    channels = [2, 1, 0] if image.shape[-1] == 3 else [2, 1, 0, 3]
    return Image.fromarray(np.ascontiguousarray(image[..., channels])).convert("RGB")


def _shape(value: Any) -> list[int] | None:
    shape = getattr(value, "shape", None)
    if shape is None:
        return None
    return [int(dimension) for dimension in shape]


def _plain(value: Any) -> Any:
    """Serialize configuration only; do not inspect GPU tensors implicitly."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "to_dict"):
        return _plain(value.to_dict())
    return {"unserialized_type": type(value).__name__}


def _token_rows(value: Any) -> list[list[int]]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [[int(token) for token in row] for row in value]


def _eos_ids(value: Any) -> set[int] | None:
    if value is None:
        return None
    if isinstance(value, int):
        return {value}
    if isinstance(value, (list, tuple)) and all(isinstance(item, int) for item in value):
        return set(value)
    return None


def _termination(tokens: list[int], parameters: Mapping[str, Any]) -> dict[str, Any]:
    eos = _eos_ids(parameters.get("eos_token_id"))
    positions = [index for index, token in enumerate(tokens) if eos and token in eos]
    limit = parameters.get("max_new_tokens")
    reached = len(tokens) >= limit if isinstance(limit, int) else None
    observed = bool(positions) if eos is not None else None
    # Tensor row length may include right padding after another batch item ends.
    pad = parameters.get("pad_token_id")
    padding = None
    unpadded = None
    if positions:
        tail = tokens[positions[0] + 1:]
        if all(token == pad for token in tail):
            padding = len(tail)
            unpadded = positions[0] + 1
    return {"stop_reason": "unknown", "stop_reason_scope": "HF stopping criteria not exposed",
            "eos_token_observed": observed, "eos_positions_zero_based": positions,
            "length_limit_reached": reached, "padding_after_first_eos_tokens": padding,
            "generated_tokens_through_first_eos": unpadded,
            "possible_length_truncation": reached and not observed if observed is not None else None}


class PaddleGenerationCollector:
    """One page of observations; no text/token output retained after finish."""

    def __init__(self) -> None:
        self._page: Any = None
        self._request_id: str | None = None
        self._batches: list[dict[str, Any]] = []
        self._next_region = 0

    def begin_page(self, page: Any = None, request_id: str | None = None) -> None:
        self._page, self._request_id = page, request_id
        self._batches.clear()
        self._next_region = 0

    def _batch(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        regions = []
        for item in data:
            image = item["image"]
            regions.append({"region_index": self._next_region, "query": item.get("query", ""),
                            "input_array_shape": _shape(image),
                            "input_type": type(image).__name__,
                            "bgr_to_pil_rgb": type(image).__name__ == "ndarray"})
            self._next_region += 1
        batch: dict[str, Any] = {"batch_index": len(self._batches), "regions": regions,
                                "generations": [], "status": "running"}
        self._batches.append(batch)
        return batch

    def finish_page(self) -> dict[str, Any]:
        """Called outside native processing timing, including on parse failure."""
        batches, self._batches = self._batches, []
        for batch in batches:
            for generation in batch["generations"]:
                outputs = generation.pop("_outputs", None)
                config = generation.pop("_generation_config", None)
                kwargs = generation.pop("_generate_kwargs", {})
                try:
                    parameters = _plain(config) if config is not None else {}
                    parameters.update(_plain(kwargs))
                    generation["effective_generation_parameters"] = parameters
                    generation["effective_parameters_scope"] = "model GenerationConfig plus SDK kwargs; HF runtime stop rules unknown"
                    if outputs is not None:
                        rows = _token_rows(outputs)
                        prompt_lengths = generation["prompt_token_lengths"]
                        generation["regions"] = [
                            {"region_index": batch["regions"][index]["region_index"],
                             "output_sequence_tokens_before_prompt_trim": len(row),
                             "prompt_tokens_removed": prompt_lengths[index],
                             "generated_tokens_after_prompt_trim": len(row[prompt_lengths[index]:]),
                             **_termination(row[prompt_lengths[index]:], parameters)}
                            for index, row in enumerate(rows)
                        ]
                except Exception as exc:
                    # Observation failure never changes or retries native output.
                    generation["observation_error"] = f"{type(exc).__name__}: {exc}"
        return {"schema": "paddle-region-generation-v1", "page": self._page,
                "request_id": self._request_id, "software_versions": dict(SUPPORTED_VERSIONS),
                "token_inspection_timing": "after_native_processing_clock",
                "region_location_scope": "predictor batch order; SDK layout IDs not exposed here",
                "batches": batches}


def install_paddle_compat(
    collector: PaddleGenerationCollector | None = None, *,
    config: Mapping[str, Any] | None = None,
    versions: Mapping[str, str] | None = None, predictor_class: Any = None,
) -> PaddleGenerationCollector:
    """Install before PaddleOCRVL construction; injected class is synthetic-only."""
    settings = config or {}
    if settings.get("paddle_color_policy", "bgr-to-rgb-v1") != "bgr-to-rgb-v1":
        raise ValueError("Paddle native color policy must be bgr-to-rgb-v1")
    if settings.get("paddle_max_new_tokens", MAX_NEW_TOKENS) != MAX_NEW_TOKENS:
        raise ValueError("Paddle native max_new_tokens must remain 4096")
    if settings.get("paddle_generation_observation", True) is not True:
        raise ValueError("Paddle native generation observation must be enabled")
    actual = dict(versions) if versions is not None else {
        name: importlib.metadata.version(name) for name in SUPPORTED_VERSIONS
    }
    if actual != SUPPORTED_VERSIONS:
        raise ValueError(f"Paddle compatibility requires {SUPPORTED_VERSIONS}; found {actual}")
    if predictor_class is None:
        from paddlex.inference.models.doc_vlm.predictor import DocVLMTransformersPredictor
        predictor_class = DocVLMTransformersPredictor
    collector = collector or PaddleGenerationCollector()
    state = predictor_class.__dict__.get("_moparse_paddle_compat")
    if state is not None:
        state["collector"] = collector
        return collector
    state = {"collector": collector}
    original_process = predictor_class.process
    original_postprocess = predictor_class.postprocess
    own_generate = predictor_class.__dict__.get("generate")

    @functools.wraps(original_process)
    def process(instance: Any, data: list[dict[str, Any]], *args: Any, **kwargs: Any) -> Any:
        if not str(instance.model_name).startswith(("PaddleOCR-VL-1.5", "PaddleOCR-VL-1.6")):
            return original_process(instance, data, *args, **kwargs)
        observer = getattr(instance, "_moparse_generation_collector", state["collector"])
        batch = observer._batch(data)
        # max_new_tokens is the first optional positional argument in 3.7.2.
        if args:
            requested_limit = args[0]
        else:
            requested_limit = kwargs.get("max_new_tokens")
        token = _CURRENT.set(batch)
        try:
            if requested_limit not in {None, MAX_NEW_TOKENS}:
                raise ValueError("Paddle region max_new_tokens differs from frozen 4096")
            if args:
                args = (MAX_NEW_TOKENS, *args[1:])
            else:
                kwargs["max_new_tokens"] = MAX_NEW_TOKENS
            converted = [{**item, "image": region_bgr_to_pil(item["image"])} for item in data]
            result = original_process(instance, converted, *args, **kwargs)
            batch["status"] = "completed"
            return result
        except BaseException as exc:
            batch.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            _CURRENT.reset(token)

    def generate(instance: Any, model_inputs: Any, generate_kwargs: Any) -> Any:
        batch = _CURRENT.get()
        record: dict[str, Any] | None = None
        if batch is not None:
            record = {"prompt_token_lengths": [len(row) for row in model_inputs["input_ids"]],
                      "input_shapes": {key: _shape(value) for key, value in model_inputs.items()},
                      "_generate_kwargs": dict(generate_kwargs),
                      "_generation_config": getattr(instance.infer, "generation_config", None),
                      "status": "running"}
            batch["generations"].append(record)
        try:
            # Resolve the inherited method at call time so separately installed
            # admission/CUDA Graph probes on the base class remain active.
            output = (own_generate(instance, model_inputs, generate_kwargs) if own_generate is not None
                      else super(predictor_class, instance).generate(model_inputs, generate_kwargs))
            if record is not None:
                record.update(_outputs=output, output_shape=_shape(output), status="completed")
            return output
        except BaseException as exc:
            if record is not None:
                record.update(status="failed", error_type=type(exc).__name__)
            raise

    @functools.wraps(original_postprocess)
    def postprocess(instance: Any, outputs: Any, **kwargs: Any) -> Any:
        result = original_postprocess(instance, outputs, **kwargs)
        batch = _CURRENT.get()
        if batch is not None and batch["generations"]:
            batch["generations"][-1]["decoded_characters_after_prompt_trim"] = [
                len(text) if isinstance(text, str) else None for text in result
            ]
            batch["generations"][-1]["decode_options"] = {
                "skip_special_tokens": True if kwargs.get("skip_special_tokens") is None
                else kwargs["skip_special_tokens"], "clean_up_tokenization_spaces": False}
        return result

    predictor_class.process = process
    predictor_class.generate = generate
    predictor_class.postprocess = postprocess
    predictor_class._moparse_paddle_compat = state
    return collector
