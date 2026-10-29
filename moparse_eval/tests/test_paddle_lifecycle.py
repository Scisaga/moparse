"""Real signal/HTTP behavior with a synthetic inference implementation only."""

from __future__ import annotations

import json
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path


def test_sigterm_drains_an_issued_native_request_before_process_exit(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    source = '''
import sys,time
from pathlib import Path
from moparse_eval.paddle_server import serve_owned
root=Path(sys.argv[1])
class Fake:
    def parse(self, request):
        (root/'started').touch()
        while not (root/'release').exists(): time.sleep(.01)
        return {'request_id':request['request_id'],'original_request_returned':True}
    def close(self): (root/'closed').touch()
serve_owned(Fake,'synthetic',('127.0.0.1',int(sys.argv[2])))
'''
    process = subprocess.Popen([sys.executable, "-c", source, str(tmp_path), str(port)],
                               cwd=Path(__file__).resolve().parents[2],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result, errors = [], []
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 5
        while True:
            try:
                with opener.open(f"http://127.0.0.1:{port}/v1/models", timeout=0.2) as response:
                    assert json.load(response)["data"][0]["id"] == "synthetic"
                break
            except OSError:
                assert time.monotonic() < deadline
                time.sleep(0.01)

        def issue_original():
            try:
                request = urllib.request.Request(f"http://127.0.0.1:{port}/parse-page",
                    data=json.dumps({"request_id": "one-issued-request"}).encode(),
                    headers={"Content-Type": "application/json"})
                with opener.open(request, timeout=5) as response:
                    result.append(json.load(response))
            except Exception as exc:
                errors.append(exc)

        request_thread = threading.Thread(target=issue_original)
        request_thread.start()
        while not (tmp_path / "started").exists():
            assert time.monotonic() < deadline
            time.sleep(0.01)
        process.send_signal(signal.SIGTERM)
        time.sleep(0.15)
        assert process.poll() is None
        assert not (tmp_path / "closed").exists()
        (tmp_path / "release").touch()
        request_thread.join(timeout=5)
        assert not request_thread.is_alive() and not errors
        assert result == [{"request_id": "one-issued-request", "original_request_returned": True}]
        assert process.wait(timeout=5) == 0
        assert (tmp_path / "closed").exists()
        assert b'"all_original_request_threads_joined": true' in process.stdout.read()
    finally:
        (tmp_path / "release").touch()
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=5)
