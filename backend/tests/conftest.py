"""Shared pytest fixtures for deterministic backend test runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import Settings, reset_settings


@pytest.fixture(autouse=True)
def _isolate_settings_from_local_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prevent local shell/env-file state from leaking into tests.

    The repo often has a populated ``backend/.env`` and developers may also
    export runtime env vars in their shell. Tests should only see the values
    they set explicitly.
    """

    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)

    monkeypatch.setenv(
        "PIPELINEHEALER_ENV_FILE_PATH",
        str(tmp_path / "missing-test-settings.env"),
    )
    reset_settings()
    yield
    reset_settings()
