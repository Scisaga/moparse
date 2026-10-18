import hashlib
import json

import pytest

from benchmark.tools.check_public_format import check, html_table_leaks


@pytest.mark.parametrize(
    "content",
    [
        '<table><tr><td>42</td></tr></table>',
        '<TABLE border="1"><TR><TH>Year</TH></TR>',
        '<div>caption<table><tr><td>42</td></tr></table></div>',
        'text <td>42</td> after',
        '<table><tr><th>header</td><td>42',
    ],
)
def test_visible_table_markup_is_a_contract_failure(content):
    assert html_table_leaks(content)


@pytest.mark.parametrize(
    "content",
    [
        '| year | amount |\n| --- | --- |\n| 2026 | 42 |\n',
        '```text\r\n<table><td>original literal</td>\r\n```\r\n',
        'Literal `<table>` example.',
        '<!-- table-structure: {"text":"<table>"} -->',
        'A <tableau> word.',
    ],
)
def test_faithful_GFM_and_nonrendered_original_literals_are_not_HTML(content):
    assert not html_table_leaks(content)


def test_captured_partial_quality_remains_partial_and_byte_identity_is_verified(tmp_path):
    case = tmp_path / 'cases' / 'doc'
    case.mkdir(parents=True)
    raw = b'```text\r\n<table>source literal\r\n```\r\n'
    (case / 'result.md').write_bytes(raw)
    run = {'cases': [{'id': 'doc', 'status': 'partial', 'capture_status': 'completed',
                      'MD_SHA256': hashlib.sha256(raw).hexdigest()}]}
    (tmp_path / 'run.json').write_text(json.dumps(run))
    observed = check(tmp_path)
    assert observed['pass']
    assert observed['documents'][0]['actual_API_status'] == 'partial'
    assert observed['documents'][0]['original_strict_table_substring_absent'] is False
    assert (case / 'result.md').read_bytes() == raw
    (case / 'result.md').write_bytes(raw + b'changed')
    with pytest.raises(ValueError, match='SHA'):
        check(tmp_path)
