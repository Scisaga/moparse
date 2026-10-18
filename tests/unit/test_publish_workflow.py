"""Release invariants for separately built parser and native-model images."""
import ast
import re
import shlex
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def workflow():
    return yaml.safe_load((ROOT / '.github/workflows/docker-publish.yml').read_text())


def test_model_images_publish_only_after_verified_main_and_use_same_revision():
    jobs = workflow()['jobs']
    main, models = jobs['publish'], jobs['publish-model-images']
    assert models['needs'] == ['publish']
    assert 'success' in main['if'] and 'workflow_run' in main['if']
    assert main['outputs']['sha'] == '${{ steps.revision.outputs.sha }}'
    checkout = next(step for step in models['steps'] if step.get('uses', '').startswith('actions/checkout@'))
    assert checkout['with']['ref'] == '${{ needs.publish.outputs.sha }}'
    metadata = next(step for step in models['steps'] if step.get('id') == 'meta')['with']
    assert 'org.opencontainers.image.revision=${{ needs.publish.outputs.sha }}' in metadata['labels']
    main_metadata = next(step for step in main['steps'] if step.get('id') == 'meta')['with']
    assert metadata['tags'].replace('needs.publish.outputs.short_sha', 'steps.revision.outputs.short_sha') == main_metadata['tags']


def test_each_dependent_image_build_and_push_uses_its_reviewed_dockerfile():
    models = workflow()['jobs']['publish-model-images']
    axes = models['strategy']['matrix']['include']
    assert {(item['image'], item['dockerfile']) for item in axes} == {
        ('moparse-native-worker', 'Dockerfile.native-worker'),
        ('moparse-mineru-vllm', 'Dockerfile.mineru-vllm'),
    }
    for item in axes:
        assert (ROOT / item['dockerfile']).is_file()
    builds = [step for step in models['steps'] if step.get('uses', '').startswith('docker/build-push-action@')]
    assert len(builds) == 2
    assert all(step['with']['file'] == '${{ matrix.dockerfile }}' for step in builds)
    assert builds[0]['with']['push'] is False
    assert builds[0]['with']['load'] == "${{ matrix.smoke == 'cpu-native' }}"
    assert builds[1]['with']['push'] is True
    assert builds[1]['with']['provenance'] == 'mode=max'
    assert builds[1]['with']['sbom'] is True
    push_index = models['steps'].index(builds[1])
    gate = models['steps'][push_index - 1]
    assert 'git ls-remote' in gate['run'] and 'refs/heads/main' in gate['run']
    assert 'exit 1' in gate['run']
    assert gate['env']['VERIFIED_SHA'] == '${{ needs.publish.outputs.sha }}'


def test_hosted_checks_verify_patch_and_sdk_without_starting_gpu_models():
    steps = workflow()['jobs']['publish-model-images']['steps']
    smoke = {step['if']: step['run'] for step in steps
             if 'run' in step and step.get('if', '').startswith('matrix.smoke')
             and '--entrypoint' in step['run']}
    cpu = smoke["matrix.smoke == 'cpu-native'"]
    assert 'verify_patch()' in cpu and 'PATCHED_SHA256' in cpu
    assert 'find_spec("torch") is None' in cpu
    assert "matrix.smoke == 'gpu-sdk-import'" not in smoke
    assert all('--network none' in value and '--gpus' not in value for value in smoke.values())
    # A real Dockerfile RUN executes the Python import while building; a grep
    # or a workflow log message cannot replace that check.
    dockerfile = (ROOT / 'Dockerfile.mineru-vllm').read_text()
    logical = re.sub(r'\\\n', ' ', dockerfile)
    command = next(line.removeprefix('RUN ') for line in logical.splitlines()
                   if line.startswith('RUN ') and 'python3 -c' in line)
    args = shlex.split(command)
    code = args[args.index('-c') + 1]
    tree = ast.parse(code)
    assert any(isinstance(node, ast.ImportFrom) and node.module == 'mineru_vl_utils'
               and any(alias.name == 'MinerULogitsProcessor' for alias in node.names)
               for node in ast.walk(tree))
    assert len([node for node in ast.walk(tree) if isinstance(node, ast.Assert)]) == 2
    assert '2.0.7' in code and 'callable(MinerULogitsProcessor)' in code
