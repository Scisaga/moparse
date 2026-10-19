from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


def make_settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)


def test_health_settings_use_the_package_release_version(monkeypatch):
    from app import __version__

    monkeypatch.delenv("VERSION", raising=False)
    assert make_settings().version == __version__


def test_public_config_never_contains_secrets(tmp_path: Path) -> None:
    settings = make_settings(
        data_dir=tmp_path,
        api_key="public-secret",
        admin_token="admin-secret",
        glm_ocr_api_key="glm-secret",
    )

    serialized = repr(settings.public_config())
    assert "public-secret" not in serialized
    assert "admin-secret" not in serialized
    assert "glm-secret" not in serialized


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


def test_selected_pdf_pipeline_defaults_are_exposed_consistently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("DOCLING_DEVICE", "DOCLING_DO_CELL_MATCHING", "DOCLING_PDF_BACKEND",
                 "DOCLING_TABLE_MODE", "GLM_SDK_ENABLED", "GLM_SDK_ORIENTATION_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    settings = make_settings()

    assert settings.docling_device == "cpu"
    assert settings.docling_do_cell_matching is False
    assert settings.docling_pdf_backend == "pypdfium"
    assert settings.docling_table_mode == "accurate"
    assert settings.glm_sdk_enabled is True
    assert settings.glm_sdk_orientation_enabled is True
    public = settings.public_config()
    assert public["docling_pdf_backend"] == "pypdfium"
    assert public["docling_do_cell_matching"] is False
    assert public["glm_sdk_orientation_enabled"] is True
