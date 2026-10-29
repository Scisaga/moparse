"""Bounded native CUDA Graph probes, installed only in research workers."""

from __future__ import annotations

import copy
from collections import OrderedDict
from typing import Any

from .runtime import PreparationError, bounded_cuda_graph_trial


class TensorGraphForward:
    """Retain successful fixed-shape graphs and replay with fresh tensor values."""
    def __init__(self, function: Any, evidence: list[dict[str, Any]], label: str) -> None:
        self.function, self.evidence, self.label = function, evidence, label
        self.graphs: OrderedDict[Any, Any] = OrderedDict()
        self.failure: str | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        import torch
        from torch.utils._pytree import tree_flatten, tree_map, tree_unflatten
        if self.failure:
            return self.function(*args, **kwargs)
        leaves, specification = tree_flatten((args, kwargs))
        def signature(value: Any) -> Any:
            if torch.is_tensor(value):
                if not value.is_cuda:
                    raise TypeError("native forward contains CPU tensors with unproven capture control flow")
                return (tuple(value.shape), value.dtype, value.device)
            if value is None or isinstance(value, (str, int, float, bool)):
                return (type(value), value)
            raise TypeError(f"native forward contains mutable {type(value).__name__}")
        try:
            key = (str(specification), tuple(signature(value) for value in leaves))
            if key not in self.graphs:
                if len(self.graphs) >= 4:
                    self.graphs.popitem(last=False)
                static = [value.detach().clone() if torch.is_tensor(value) else value for value in leaves]
                static_args, static_kwargs = tree_unflatten(static, specification)
                stream = torch.cuda.Stream()
                stream.wait_stream(torch.cuda.current_stream())
                with torch.cuda.stream(stream), torch.inference_mode():
                    for _ in range(2):
                        reference = self.function(*static_args, **static_kwargs)
                torch.cuda.current_stream().wait_stream(stream)
                torch.cuda.synchronize()
                graph = torch.cuda.CUDAGraph()
                with torch.inference_mode(), torch.cuda.graph(graph):
                    output = self.function(*static_args, **static_kwargs)
                graph.replay()
                torch.cuda.synchronize()
                reference_leaves, reference_spec = tree_flatten(reference)
                output_leaves, output_spec = tree_flatten(output)
                if reference_spec != output_spec:
                    raise TypeError("capture changed native output structure")
                for before, after in zip(reference_leaves, output_leaves, strict=True):
                    if torch.is_tensor(before):
                        torch.testing.assert_close(before, after)
                    elif before is not None and not isinstance(before, (str, int, float, bool)):
                        raise TypeError("native output is not safely replayable as tensor leaves")
                self.graphs[key] = (static, graph, output)
                self.evidence.append({"component": self.label, "status": "captured_and_replayed",
                    "graphs_enabled": True, "input_shapes": [list(value.shape) for value in leaves if torch.is_tensor(value)],
                    "warmups": 2, "replays": 1})
            static, graph, output = self.graphs[key]
            for destination, source in zip(static, leaves, strict=True):
                if torch.is_tensor(source):
                    destination.copy_(source)
            graph.replay()
            return tree_map(lambda value: value.clone() if torch.is_tensor(value) else value, output)
        except Exception as exc:
            self.failure = f"{type(exc).__name__}: {exc}"
            self.graphs.clear()
            self.evidence.append({"component": self.label, "status": "capture_failed",
                "graphs_enabled": False, "reason": self.failure,
                "reenable_condition": "fix recorded capture failure within the same memory budget"})
            return self.function(*args, **kwargs)


def install_paddle_trials(evidence: list[dict[str, Any]], *, admission: Any = None) -> None:
    """Probe the declared full native generation API; retain layout graphs."""
    from paddlex.inference.models.predictors.transformers_predictor import TransformersPredictor
    original_forward = TransformersPredictor.forward
    original_generate = TransformersPredictor.generate
    installed: set[int] = set()
    tried_generation: set[int] = set()

    def forward(instance: Any, model_inputs: Any) -> Any:
        if admission is not None:
            admission()
        model = instance.infer
        if id(model) not in installed:
            model.forward = TensorGraphForward(model.forward, evidence, type(instance).__name__ + ".forward")
            installed.add(id(model))
        return original_forward(instance, model_inputs)

    def generate(instance: Any, model_inputs: Any, generate_kwargs: Any) -> Any:
        if admission is not None:
            admission()
        if id(instance) not in tried_generation:
            tried_generation.add(id(instance))
            trial_kwargs = copy.deepcopy(generate_kwargs)
            trial_kwargs["max_new_tokens"] = 2
            trial_kwargs.pop("max_length", None)
            def bounded_generation() -> Any:
                import torch
                from torch.utils._pytree import tree_map
                cloned = tree_map(lambda value: value.detach().clone() if torch.is_tensor(value)
                                  else copy.deepcopy(value), model_inputs)
                return original_generate(instance, cloned, copy.deepcopy(trial_kwargs))
            trial = bounded_cuda_graph_trial(bounded_generation, (), warmups=1, replays=1)
            trial.update(component=type(instance).__name__ + ".generate", max_new_tokens=2,
                         scope="official full native generation operation")
            evidence.append(trial)
            if trial["graphs_enabled"]:
                raise PreparationError("native generation captured successfully; full-length replay binding must be implemented before execution")
        if admission is not None:
            admission()
        return original_generate(instance, model_inputs, generate_kwargs)

    TransformersPredictor.forward = forward
    TransformersPredictor.generate = generate
