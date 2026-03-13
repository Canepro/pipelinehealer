"""Storage mode selection and non-development durability guardrail tests."""

import asyncio

import pytest

from src import main as main_module
from src.config import get_settings, reset_settings
from src.storage import ActivityStorage, InMemoryStorage, PostgresStorage
from src.workflows.pipeline_healer import create_storage, resolve_storage_mode


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("STORAGE_MODE", raising=False)
    monkeypatch.delenv("COSMOS_DB_ENDPOINT", raising=False)
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("ALLOW_IN_MEMORY_STORAGE_IN_NON_DEVELOPMENT", raising=False)
    reset_settings()
    yield
    reset_settings()


def test_development_defaults_to_memory_mode() -> None:
    settings = get_settings()
    assert resolve_storage_mode(settings) == "memory"
    assert isinstance(create_storage(settings), InMemoryStorage)


def test_non_development_defaults_to_cosmos_and_fails_without_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    reset_settings()
    settings = get_settings()

    with pytest.raises(RuntimeError, match="COSMOS_DB_ENDPOINT"):
        resolve_storage_mode(settings)


def test_non_development_uses_cosmos_when_endpoint_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("COSMOS_DB_ENDPOINT", "https://example.documents.azure.com:443/")
    reset_settings()
    settings = get_settings()

    assert resolve_storage_mode(settings) == "cosmos"
    assert isinstance(create_storage(settings), ActivityStorage)


def test_non_development_rejects_memory_without_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("STORAGE_MODE", "memory")
    reset_settings()
    settings = get_settings()

    with pytest.raises(RuntimeError, match="ALLOW_IN_MEMORY_STORAGE_IN_NON_DEVELOPMENT"):
        resolve_storage_mode(settings)


def test_non_development_allows_memory_with_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("STORAGE_MODE", "memory")
    monkeypatch.setenv("ALLOW_IN_MEMORY_STORAGE_IN_NON_DEVELOPMENT", "true")
    reset_settings()
    settings = get_settings()

    assert resolve_storage_mode(settings) == "memory"
    assert isinstance(create_storage(settings), InMemoryStorage)


def test_explicit_cosmos_mode_requires_endpoint_even_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("STORAGE_MODE", "cosmos")
    reset_settings()
    settings = get_settings()

    with pytest.raises(RuntimeError, match="COSMOS_DB_ENDPOINT"):
        resolve_storage_mode(settings)


def test_explicit_postgres_mode_requires_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("STORAGE_MODE", "postgres")
    reset_settings()
    settings = get_settings()

    with pytest.raises(RuntimeError, match="POSTGRES_DSN"):
        resolve_storage_mode(settings)


def test_explicit_postgres_mode_builds_postgres_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("STORAGE_MODE", "postgres")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:pass@localhost:5432/pipelinehealer")
    reset_settings()
    settings = get_settings()

    assert resolve_storage_mode(settings) == "postgres"
    assert isinstance(create_storage(settings), PostgresStorage)


@pytest.mark.asyncio
async def test_lifespan_does_not_force_in_memory_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("STORAGE_MODE", "postgres")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:pass@localhost:5432/pipelinehealer")
    reset_settings()

    captured: dict[str, object] = {}

    class _DummyWorkflow:
        def __init__(self) -> None:
            self.storage = object()

        async def initialize(self) -> None:
            captured["initialized"] = True

        async def recover_stale_activities(self) -> int:
            return 0

        async def close(self) -> None:
            captured["closed"] = True

    def _fake_create_workflow(*, use_in_memory: bool = False) -> _DummyWorkflow:
        captured["use_in_memory"] = use_in_memory
        return _DummyWorkflow()

    async def _fake_apply_persisted_runtime_settings(storage, workflow) -> None:  # type: ignore[no-untyped-def]
        captured["applied"] = (storage, workflow)

    async def _fake_backfill_sweep_loop(workflow) -> None:  # type: ignore[no-untyped-def]
        await asyncio.sleep(3600)

    monkeypatch.setattr(main_module, "create_workflow", _fake_create_workflow)
    monkeypatch.setattr(
        main_module.dashboard,
        "apply_persisted_runtime_settings",
        _fake_apply_persisted_runtime_settings,
    )
    monkeypatch.setattr(main_module, "_backfill_sweep_loop", _fake_backfill_sweep_loop)

    test_app = main_module.create_app()
    async with main_module.lifespan(test_app):
        assert captured["use_in_memory"] is False
        assert captured["initialized"] is True

    assert "applied" in captured
    assert captured["closed"] is True
