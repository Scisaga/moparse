"""Runtime evidence must distinguish missing data from observed zero."""

from benchmark.tools.monitor_runtime import (
    Summary,
    memory_bytes,
    number,
    own_gpu_usage,
    parse_metrics,
    parse_pmon,
)


def test_missing_measurements_are_null_not_fabricated_zero():
    for value in ("-", "N/A", "[Not Supported]", "NaN", "inf", None):
        assert number(value) is None
    assert number("0 %") == 0
    assert memory_bytes("1.5GiB") == 1610612736
    assert memory_bytes("2GB") == 2_000_000_000
    assert memory_bytes("N/A") is None


def test_pmon_reads_supported_headers_and_preserves_unavailable_sm():
    rows = parse_pmon("""# gpu pid type sm mem enc dec jpg ofa fb ccpm command
# Idx # C/G % % % % % % MB MB name
0 123 C 0 - - - - - 300 0 python
1 456 C - - - - - - 500 0 python
""")
    assert rows[0]["sm_pct"] == 0
    assert rows[1]["sm_pct"] is None
    assert rows[1]["fb_MiB"] == 500


def test_only_owned_container_pids_contribute_to_gpu_fb_and_sm():
    processes = [
        {"gpu_uuid": "GPU-1", "pid": 11, "memory_MiB": 100},
        {"gpu_uuid": "GPU-1", "pid": 12, "memory_MiB": 200},
        {"gpu_uuid": "GPU-1", "pid": 90, "memory_MiB": 9000},
    ]
    pmon = [{"pid": 11, "sm_pct": 20}, {"pid": 12, "sm_pct": None}, {"pid": 90, "sm_pct": 99}]
    observed = own_gpu_usage(processes, {"parser": [11, 12], "unknown": None}, pmon)
    assert observed["parser"]["gpu_memory_MiB_by_uuid"] == {"GPU-1": 300}
    assert observed["parser"]["sm_pct_observed_sum"] == 20
    assert observed["unknown"]["gpu_memory_MiB_by_uuid"] is None
    assert observed["unknown"]["sm_pct_observed_sum"] is None
    unavailable = own_gpu_usage(None, {"parser": [11]}, None)
    assert unavailable["parser"]["gpu_memory_MiB_by_uuid"] is None
    assert unavailable["parser"]["sm_pct_observed_sum"] is None


def sample(timestamp, power):
    return {
        "monotonic": timestamp,
        "errors": [],
        "devices": [
            {
                "index": 1,
                "uuid": "GPU-1",
                "name": "test",
                "power_watts_shared_device": power,
                "utilization_gpu_pct_shared_device": None,
                "memory_used_MiB_shared_device": None,
            }
        ],
        "owned_gpu": {},
        "docker_stats": None,
        "vllm_metrics": None,
    }


def test_whole_device_energy_is_labelled_shared_and_does_not_bridge_missing_power():
    summary = Summary()
    summary.add(sample(0, 100))
    assert summary.export()["devices"]["GPU-1"]["energy_joules_shared_device"] is None
    summary.add(sample(2, 200))
    summary.add(sample(4, None))
    summary.add(sample(6, 100))
    assert summary.export()["devices"]["GPU-1"]["energy_joules_shared_device"] == 300
    summary.add(sample(8, 100))
    report = summary.export()
    assert report["devices"]["GPU-1"]["energy_joules_shared_device"] == 500
    assert report["devices"]["GPU-1"]["gpu_utilization_mean_pct_shared_device"] is None
    assert "Shared whole-device" in report["energy_scope"]


def test_vllm_counters_preserve_labels_and_report_resets():
    metrics = parse_metrics("""# TYPE vllm:generation_tokens_total counter
vllm:generation_tokens_total{model_name="test"} 20
vllm:num_preemptions_total{model_name="test"} 0
vllm:kv_cache_usage_perc{model_name="test"} 0.5
vllm:generation_tokens_total{model_name="missing"} NaN
unrelated_metric 99
""")
    assert len(metrics) == 4
    assert metrics[-1]["value"] is None
    summary = Summary()
    first = sample(0, None)
    first["vllm_metrics"] = metrics[:1]
    summary.add(first)
    second = sample(2, None)
    second["vllm_metrics"] = [dict(metrics[0], value=25)]
    summary.add(second)
    third = sample(4, None)
    third["vllm_metrics"] = [dict(metrics[0], value=2)]
    summary.add(third)
    counter = summary.export()["vllm_metrics"][0]
    assert counter["observed_counter_increase"] == 5
    assert counter["counter_resets"] == 1
    assert counter["labels"] == '{model_name="test"}'


def test_private_vllm_metrics_ignore_ambient_proxy(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from benchmark.tools.monitor_runtime import vllm_metrics

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'vllm:num_requests_running{model_name="test"} 2\n')

        def log_message(self, *_args):
            pass

    for key in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.setenv(key, "http://127.0.0.1:1")
    for key in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(key, "")
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        result = vllm_metrics(f"http://127.0.0.1:{server.server_port}")
        assert result[0]["name"] == "vllm:num_requests_running" and result[0]["value"] == 2
    finally:
        server.server_close()
        thread.join(timeout=2)
