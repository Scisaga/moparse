from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


def make_settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)


def test_public_config_never_contains_secrets(tmp_path: Path) -> None:
    settings = make_settings(
        data_dir=tmp_path,
        api_key="public-secret",
        admin_token="admin-secret",
        glm_ocr_api_key="glm-secret",
        vlm_api_key="vlm-secret",
    )

    serialized = repr(settings.public_config())
    assert "public-secret" not in serialized
    assert "admin-secret" not in serialized
    assert "glm-secret" not in serialized
    assert "vlm-secret" not in serialized


@pytest.mark.parametrize("device", ["cpu", "auto", "mps", "cuda", "cuda:1"])
def test_docling_device_accepts_supported_values(device: str) -> None:
    assert make_settings(docling_device=device).docling_device == device


def test_docling_device_rejects_invalid_index() -> None:
    with pytest.raises(ValidationError):
        make_settings(docling_device="cuda:gpu-1")


def test_sync_limits_cannot_exceed_global_limits() -> None:
    with pytest.raises(ValidationError, match="SYNC_MAX_BYTES"):
        make_settings(max_upload_bytes=100, sync_max_bytes=101)
    with pytest.raises(ValidationError, match="SYNC_MAX_UNITS"):
        make_settings(max_content_units=2, sync_max_units=3)


def test_docling_cached_converter_pool_is_bounded() -> None:
    settings = make_settings(parser_workers=4, docling_page_workers=8)
    assert settings.parser_workers * settings.docling_page_workers == 32

    with pytest.raises(ValidationError, match="cached converters"):
        make_settings(parser_workers=5, docling_page_workers=8)


def test_mcp_host_allowlist_adds_port_patterns() -> None:
    settings = make_settings(mcp_allowed_hosts="localhost,parser:12303")
    assert settings.mcp_allowed_host_list == ["localhost", "localhost:*", "parser:12303"]


def test_media_descriptions_disable_reasoning_by_default() -> None:
    settings = make_settings()
    assert settings.media_vlm_reasoning_effort == "none"
    assert settings.video_summary_reasoning_effort == "none"


def test_document_vlm_routes_have_cost_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "VLM_SIGNATURE_ENABLED",
        "VLM_TABLE_FULL_ENABLED",
        "VLM_TABLE_TARGETED_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = make_settings()

    assert settings.vlm_signature_enabled is False
    assert settings.vlm_table_full_enabled is False
    assert settings.vlm_table_targeted_enabled is True
    public = settings.public_config()
    assert public["vlm_signature_enabled"] is False
    assert public["vlm_table_full_enabled"] is False
    assert public["vlm_table_targeted_enabled"] is True


def test_document_vlm_route_flags_are_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VLM_SIGNATURE_ENABLED", "1")
    monkeypatch.setenv("VLM_TABLE_FULL_ENABLED", "true")
    monkeypatch.setenv("VLM_TABLE_TARGETED_ENABLED", "0")

    settings = make_settings()

    assert settings.vlm_signature_enabled is True
    assert settings.vlm_table_full_enabled is True
    assert settings.vlm_table_targeted_enabled is False
    assert settings.public_config()["vlm_signature_enabled"] is True
    assert settings.public_config()["vlm_table_full_enabled"] is True
    assert settings.public_config()["vlm_table_targeted_enabled"] is False
