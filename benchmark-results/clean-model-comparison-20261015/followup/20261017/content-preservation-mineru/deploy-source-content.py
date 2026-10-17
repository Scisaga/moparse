"""Deploy only the accepted API; preserve old results and the live OCR services."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
ROOT = next(parent for parent in HERE.parents if (parent / ".git").exists())
PRIVATE = Path("/root/.cache/mosaic-parse-deploy/20261017/source-content")
DATA = Path("/var/lib/docker/volumes/mosaicparse-data/_data")
BASE = "http://10.0.6.22:12303"
TAG = "mosaic-parse:0.4.0-source-content-20261017-r2"
CONTAINERS = ("mosaicparse", "docling_glm_ocr_sdk", "docling_glm_ocr")


def read(path):
    return json.loads(Path(path).read_text())


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(name):
    value = read_inspect(name)
    return {
        "ID": value["Id"],
        "image": value["Image"],
        "started": value["State"]["StartedAt"],
        "restart_count": value["RestartCount"],
    }


def read_inspect(name):
    return json.loads(subprocess.check_output(["docker", "inspect", name], text=True))[0]


def active_jobs():
    with sqlite3.connect(f"file:{DATA / 'jobs.db'}?mode=ro", uri=True) as connection:
        return connection.execute(
            "select count(*) from jobs where status in ('queued','running')"
        ).fetchone()[0]


def existing_outputs():
    return {
        str(path.relative_to(DATA)): sha(path)
        for pattern in ("jobs/*/output/**/*", "jobs/*/assets/**/*", "jobs/*/media/**/*")
        for path in sorted(DATA.glob(pattern))
        if path.is_file()
    }


def main():
    expected = read(HERE / "candidate-image-ready-and-source.json")
    assert expected["OpenAPI_JSON_same_as_r3_production"] is True
    assert expected["frozen_source_files_matching"] == 53
    assert expected["locked_dependency_versions_and_model_configuration_unchanged"] is True
    capture = HERE / "candidate-full10-http"
    summary = read(capture / "summary.json")
    assert read(capture / "run-completion.json")["complete_capture"] is True
    assert len(summary) == 10 and sum(case["page_count"] for case in summary) == 502
    assert all(case["status"] == "completed" and not case.get("asset_errors") for case in summary)
    scores = read(capture / "scoring/score-summary.json")["frozen"]
    assert scores["core_numeric"]["pass"] == 209 and scores["core_period_pass"] == 209
    assert scores["financial30"]["pass"] == 30 and scores["funding31"]["pass"] == 31
    assert scores["funding7_bound"] == 7
    assert (
        scores["supplements"]["normal33"]["literal"]["literal_row_and_complete_header_pass"] == 33
    )
    assets = read(capture / "source-assets-audit.json")
    assert assets["status"] == "pass" and assets["expected_routed_source_images"] == 69
    office = read(HERE / "candidate-office-source-acceptance-final.json")
    assert office["pass"] is True and office["passed_checks"] == office["total_checks"] == 8
    assert active_jobs() == 0
    before = {name: identity(name) for name in CONTAINERS}
    initial = read(HERE / "production-before.json")["containers"]
    assert before == initial, (
        "Live deployment changed since the baseline; inspect before replacing it"
    )
    assert (
        subprocess.check_output(
            ["docker", "image", "inspect", TAG, "--format", "{{.Id}}"], text=True
        ).strip()
        == expected["image_ID"]
    )
    files = {
        str(path.relative_to(ROOT)): sha(path) for path in sorted((ROOT / "app").rglob("*.py"))
    }
    assert files == expected["actual"]["files"]
    old_outputs = existing_outputs()
    save("production-old-output-hashes-before.json", old_outputs)
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = PRIVATE / ".env.production-before-source-content"
    assert not backup.exists(), "Do not overwrite a deployment backup"
    shutil.copyfile(ROOT / ".env", backup)
    backup.chmod(0o600)
    database_backup = PRIVATE / "jobs.before-source-content.db"
    with sqlite3.connect(f"file:{DATA / 'jobs.db'}?mode=ro", uri=True) as source:
        with sqlite3.connect(database_backup) as destination:
            source.backup(destination)
    database_backup.chmod(0o600)
    original = backup.read_text()
    assert len(re.findall(r"(?m)^MOSAICPARSE_IMAGE=.*$", original)) == 1
    selected = re.sub(r"(?m)^MOSAICPARSE_IMAGE=.*$", f"MOSAICPARSE_IMAGE={TAG}", original)
    values = dotenv_values(stream=__import__("io").StringIO(selected))
    environment = os.environ.copy()
    for key in values:
        environment.pop(key, None)
    selected_path = PRIVATE / ".env.production-source-content"
    selected_path.write_text(selected)
    selected_path.chmod(0o600)
    compose = [
        "docker",
        "compose",
        "--project-directory",
        str(ROOT),
        "--env-file",
        str(selected_path),
        "--profile",
        "glm-sdk",
    ]
    config = json.loads(
        subprocess.check_output(
            compose + ["config", "--format", "json"], env=environment, text=True
        )
    )
    assert config["services"]["mosaicparse"]["image"] == TAG
    assert active_jobs() == 0
    save(
        "production-deployment-start.json",
        {
            "UTC": dt.datetime.now(dt.UTC).isoformat(),
            "before": before,
            "active_jobs": 0,
            "existing_output_files": len(old_outputs),
            "environment_change": ["MOSAICPARSE_IMAGE"],
            "private_backups_retained": True,
        },
    )
    shutil.copyfile(selected_path, ROOT / ".env")
    (ROOT / ".env").chmod(0o600)
    with (HERE / "production-compose-update.log").open("w") as log:
        subprocess.run(
            compose + ["up", "-d", "--no-deps", "--force-recreate", "mosaicparse"],
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    headers = {"X-API-Key": values["API_KEY"]} if values.get("API_KEY") else {}
    with httpx.Client(base_url=BASE, headers=headers, trust_env=False, timeout=15) as client:
        for _ in range(180):
            try:
                response = client.get("/ready")
                if response.status_code == 200:
                    save("production-ready-after.json", response.json())
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError(
                "New API did not become ready; private rollback environment is retained"
            )
        save("production-backends-after.json", client.get("/v1/backends").json())
        original_openapi = (
            HERE / "candidate-full10-http/openapi-json-before-response-body.bin"
        ).read_bytes()
        assert json.loads(client.get("/openapi.json").content) == json.loads(original_openapi)
        old_http = []
        for job in ("job_01M54PBZSMH249W7NWXT638W8K", "job_01M54S6SZB4PH061X16NW8TVCQ"):
            result = client.get(f"/v1/content/jobs/{job}/result")
            actual_sha = hashlib.sha256(result.content).hexdigest()
            assert result.status_code == 200
            assert actual_sha == old_outputs[f"jobs/{job}/output/result.md"]
            old_http.append({"job": job, "HTTP": result.status_code, "MD_SHA256": actual_sha})
        save("production-user-original-jobs-after.json", old_http)
    actual = json.loads(
        subprocess.check_output(
            [
                "docker",
                "exec",
                "mosaicparse",
                "python",
                "-c",
                "import json,hashlib,importlib.metadata as m; from pathlib import Path; "
                "from app.config import Settings; s=Settings(); "
                "print(json.dumps({'files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() "
                "for p in sorted(Path('app').rglob('*.py'))},'versions':{n:m.version(n) "
                "for n in ['docling','docling-core','docling-ibm-models','pypdfium2','torch','transformers','markdown-it-py']},"
                "'config':s.public_config(),'SDK_DPI':s.glm_sdk_render_scale*72}))",
            ],
            text=True,
        )
    )
    assert actual == expected["actual"]
    after = {name: identity(name) for name in CONTAINERS}
    assert after["mosaicparse"]["image"] == expected["image_ID"]
    assert all(after[name] == before[name] for name in CONTAINERS[1:])
    changed = [
        path
        for path, digest in old_outputs.items()
        if not (DATA / path).is_file() or sha(DATA / path) != digest
    ]
    assert not changed, changed
    save(
        "production-deployment.json",
        {
            "UTC": dt.datetime.now(dt.UTC).isoformat(),
            "base_url": BASE,
            "before": before,
            "after": after,
            "image_tag": TAG,
            "actual": actual,
            "runtime_source_files_matching": len(files),
            "SDK_and_GLM_instances_unchanged": True,
            "OpenAPI_JSON_unchanged": True,
            "existing_output_files_checked": len(old_outputs),
            "changed_old_output_files": changed,
            "active_jobs_after": active_jobs(),
            "full_predeployment_HTTP_pages": 504,
            "postdeployment_validation": [
                "production-office-http",
                "production-boundary-http",
                "production-native-http",
            ],
        },
    )
    print("Accepted API deployed; source, configuration, readiness and old output bytes verified.")


if __name__ == "__main__":
    main()
