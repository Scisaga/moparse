#!/usr/bin/env python3
"""Controlled tensor-only GLM-OCR MRoPE probe for the frozen vLLM 0.19.1 image.

No model, document, corpus file, OCR call, or network request is used. The caller
must first own the authorized GPU 1 maintenance window, and run this inside a
container exposing ONLY physical GPU 1. cuda:0 below is that mapped device.

Example inside the isolated image (bind this file read-only at /probe.py):
    python3 /probe.py --output /output/mrope-probe.json

The default CUDA path is expected to fail GPT-J pairing on this unpatched
version. Exit 0 means the diagnostic was completed, native dispatch and its
CUDA Graph capture/replays passed, and the expected bad-path signature was
observed; it does not mean original model inference was correct.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be a new path; historical evidence is not overwritten")

    import torch
    from vllm.config import CompilationConfig, VllmConfig, set_current_vllm_config
    from vllm.model_executor.layers.rotary_embedding.mrope import MRotaryEmbedding

    version = importlib.metadata.version("vllm")
    if version != "0.19.1":
        raise RuntimeError(f"probe frozen for vLLM 0.19.1, got {version!r}")
    if torch.cuda.device_count() != 1:
        raise RuntimeError("caller must expose exactly the owned physical GPU 1")
    device = torch.device("cuda:0")
    dtype = torch.float16
    head_size, num_heads, kv_heads = 128, 16, 8
    section = [16, 24, 24]
    torch.manual_seed(314159)
    positions = {
        "multimodal_distinct_axes": torch.tensor(
            [[13, 257, 1023, 2047], [71, 139, 531, 4095], [91, 83, 1981, 8191]],
            dtype=torch.long, device=device,
        ),
        "decode_equal_axes": torch.tensor(
            [[113, 231, 977, 4091]] * 3, dtype=torch.long, device=device,
        ),
    }
    query = torch.randn(4, num_heads * head_size, device=device, dtype=dtype)
    key = torch.randn(4, kv_heads * head_size, device=device, dtype=dtype)

    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "controlled_random_tensors_only_no_model_no_corpus_no_inference",
        "software": {name: importlib.metadata.version(name) for name in
                     ("vllm", "torch", "transformers")},
        "device": {"mapped_device": str(device), "visible_count": 1,
                   "name": torch.cuda.get_device_name(device),
                   "compute_capability": list(torch.cuda.get_device_capability(device))},
        "model_shape": {"head_size": head_size, "rotary_dim": 128,
                        "num_attention_heads": num_heads, "num_key_value_heads": kv_heads,
                        "mrope_section": section, "rope_theta": 10000.0,
                        "partial_rotary_factor": 1.0, "max_position_embeddings": 16384,
                        "dtype": str(dtype)},
        "comparisons": [], "graph_trials": [], "errors": [],
    }

    def reference(rope, pos, x, neox):
        # Independent explicit pairing, using the identical rounded cache so
        # this tests pairing rather than separate sin/cos implementations.
        cache = rope.cos_sin_cache[pos]
        cos, sin = cache.chunk(2, dim=-1)
        cos = torch.cat([chunk[i] for i, chunk in enumerate(cos.split(section, dim=-1))], -1)
        sin = torch.cat([chunk[i] for i, chunk in enumerate(sin.split(section, dim=-1))], -1)
        z = x.reshape(4, -1, head_size).float()
        c, s = cos.float().unsqueeze(1), sin.float().unsqueeze(1)
        if neox:
            first, second = z.chunk(2, dim=-1)
            result = torch.cat([first * c - second * s, second * c + first * s], -1)
        else:
            first, second = z[..., 0::2], z[..., 1::2]
            result = torch.stack([first * c - second * s, second * c + first * s], -1).flatten(-2)
        return result.reshape(x.shape).to(dtype)

    def compare(actual, expected):
        if actual[1] is None:
            raise AssertionError("key unexpectedly absent")
        measurements = []
        for a, e in zip(actual, expected):
            a32, e32 = a.float(), e.float()
            delta = (a32 - e32).abs()
            def scalar(value):
                number = float(value.item())
                return number if math.isfinite(number) else None
            measurements.append({
                "finite": bool(torch.isfinite(a32).all().item()),
                "max_abs_error": scalar(delta.max()),
                "rms_error": scalar(torch.sqrt((delta * delta).mean())),
                "cosine_similarity": scalar(torch.nn.functional.cosine_similarity(
                    a32.flatten(), e32.flatten(), dim=0)),
                # Native performs FP16 intermediate arithmetic. This tolerance
                # allows its rounding and still separates the large pairing bug.
                "allclose": bool(torch.allclose(a32, e32, atol=0.008, rtol=0.002)),
            })
        return {"query": measurements[0], "key": measurements[1],
                "allclose": all(m["allclose"] and m["finite"] for m in measurements)}

    def require(ok, message):
        if not ok:
            record["errors"].append(message)

    try:
        for neox in (False, True):
            for custom_ops in (["all"], ["all", "-rotary_embedding"]):
                compilation = CompilationConfig(
                    mode=0, custom_ops=custom_ops,
                    cudagraph_mode="FULL_DECODE_ONLY",
                    cudagraph_capture_sizes=[1, 2, 3, 4], max_cudagraph_capture_size=4,
                )
                config = VllmConfig(compilation_config=compilation)
                with set_current_vllm_config(config):
                    rope = MRotaryEmbedding(
                        head_size=head_size, rotary_dim=128,
                        max_position_embeddings=16384, base=10000.0,
                        is_neox_style=neox, dtype=dtype,
                        mrope_section=section, mrope_interleaved=False,
                    ).to(device)
                    dispatch = rope._forward_method.__name__
                    disabled = "-rotary_embedding" in custom_ops
                    require(dispatch == ("forward_native" if disabled else "forward_cuda"),
                            f"unexpected dispatch {dispatch} for {custom_ops}")
                    for pos_name, pos in positions.items():
                        expected = (reference(rope, pos, query, neox), reference(rope, pos, key, neox))
                        methods = {"direct_native": rope.forward_native,
                                   "direct_cuda": rope.forward_cuda,
                                   "configured_dispatch": rope.forward}
                        observed = {}
                        for method_name, method in methods.items():
                            observed[method_name] = compare(
                                method(pos, query.clone(), key.clone()), expected)
                        torch.cuda.synchronize(device)
                        record["comparisons"].append({
                            "is_neox_style": neox, "position_case": pos_name,
                            "custom_ops_requested": custom_ops,
                            "custom_ops_effective": config.compilation_config.custom_ops,
                            "configured_forward_method": dispatch, "methods": observed,
                        })
                        require(observed["direct_native"]["allclose"], "native/reference mismatch")
                        require(observed["configured_dispatch"]["allclose"] == (neox or disabled),
                                "configured dispatch did not match expected bug/fix signature")
                        require(observed["direct_cuda"]["allclose"] == neox,
                                "direct CUDA did not match expected 0.19.1 pairing signature")

                        if disabled and not neox:
                            # Bounded capture + three replays, including changed
                            # tensor values and positions at the same static shape.
                            static_pos, static_q, static_k = pos.clone(), query.clone(), key.clone()
                            capture_stream = torch.cuda.Stream(device=device)
                            capture_stream.wait_stream(torch.cuda.current_stream(device))
                            with torch.cuda.stream(capture_stream):
                                for _ in range(3):
                                    rope(static_pos, static_q.clone(), static_k.clone())
                            capture_stream.synchronize()
                            graph = torch.cuda.CUDAGraph()
                            with torch.cuda.graph(graph, stream=capture_stream):
                                graph_out = rope(static_pos, static_q.clone(), static_k.clone())
                            capture_stream.synchronize()
                            trials = []
                            for replay_index in range(3):
                                static_q.copy_(query + replay_index * 0.125)
                                static_k.copy_(key - replay_index * 0.0625)
                                static_pos.copy_(pos + replay_index)
                                graph.replay()
                                torch.cuda.synchronize(device)
                                expected_replay = (reference(rope, static_pos, static_q, neox),
                                                   reference(rope, static_pos, static_k, neox))
                                value = compare(graph_out, expected_replay)
                                trials.append({"replay": replay_index, "comparison": value})
                                require(value["allclose"], "native rotary graph replay mismatch")
                            record["graph_trials"].append({
                                "position_case": pos_name, "capture_succeeded": True,
                                "dispatch": dispatch, "replays": trials,
                            })
                            del graph, graph_out
                    del rope
    except Exception as exc:
        record["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        record["cuda_peak_allocated_bytes"] = int(torch.cuda.max_memory_allocated(device))
        record["cuda_peak_reserved_bytes"] = int(torch.cuda.max_memory_reserved(device))
        record["diagnostic_completed_with_expected_signature"] = not record["errors"]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        print(json.dumps({"output": str(args.output), "errors": record["errors"],
                          "diagnostic_completed_with_expected_signature":
                          record["diagnostic_completed_with_expected_signature"]}))
    return 1 if record["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
