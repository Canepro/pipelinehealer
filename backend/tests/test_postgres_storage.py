"""PostgreSQL storage adapter contract tests (mocked asyncpg pool)."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from src.models import (
    ActivityRecord,
    ExternalDiagnostic,
    ExternalDiagnosticStatus,
    FailureType,
    RemediationStatus,
    utcnow,
)
from src.storage import (
    _POSTGRES_BOOTSTRAP_SQL,
    _POSTGRES_BOOTSTRAP_SQL_PATH,
    InMemoryStorage,
    PostgresStorage,
)


def _q(sql: str) -> str:
    normalized_lines = [
        line.strip()
        for line in sql.strip().splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]
    return " ".join(" ".join(normalized_lines).lower().split())


@dataclass
class _FakeState:
    activities: dict[str, dict[str, Any]] = field(default_factory=dict)
    runtime_settings: dict[str, Any] | None = None
    admin_audit: list[tuple[datetime, dict[str, Any]]] = field(default_factory=list)
    learning_queue: dict[str, dict[str, Any]] = field(default_factory=dict)
    bootstrap_count: int = 0


class _FakeConnection:
    def __init__(self, state: _FakeState) -> None:
        self._state = state

    async def execute(self, query: str, *args: Any) -> str:
        normalized = _q(query)
        if "create table if not exists ph_activities" in normalized:
            self._state.bootstrap_count += 1
            return "OK"
        if "insert into ph_activities" in normalized:
            activity_id, repository_name, status, failure_type, created_at, updated_at, payload = args
            self._state.activities[str(activity_id)] = {
                "id": str(activity_id),
                "repository_name": str(repository_name),
                "status": str(status),
                "failure_type": str(failure_type) if failure_type else None,
                "created_at": created_at,
                "updated_at": updated_at,
                "payload": json.loads(str(payload)),
            }
            return "OK"
        if "insert into ph_runtime_settings" in normalized:
            _id, _updated_at, settings_json = args
            self._state.runtime_settings = json.loads(str(settings_json))
            return "OK"
        if "insert into ph_admin_settings_audit" in normalized:
            ts, payload_json = args
            self._state.admin_audit.append((ts, json.loads(str(payload_json))))
            return "OK"
        if "insert into ph_learning_queue" in normalized:
            item_id, status, updated_at, payload_json = args
            self._state.learning_queue[str(item_id)] = {
                "status": str(status) if status is not None else "",
                "updated_at": updated_at,
                "payload": json.loads(str(payload_json)),
            }
            return "OK"
        raise AssertionError(f"Unexpected execute query: {query}")

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        normalized = _q(query)
        if "from ph_activities where id = $1" in normalized:
            row = self._state.activities.get(str(args[0]))
            if row is None:
                return None
            return {"payload": json.dumps(row["payload"])}
        if "from ph_runtime_settings where id = $1" in normalized:
            if self._state.runtime_settings is None:
                return None
            return {"settings": json.dumps(self._state.runtime_settings)}
        if "from ph_learning_queue where id = $1" in normalized:
            row = self._state.learning_queue.get(str(args[0]))
            if row is None:
                return None
            return {"payload": json.dumps(row["payload"])}
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        normalized = _q(query)
        if "from ph_activities" in normalized:
            if "status = any($1::text[])" in normalized:
                statuses = {str(value) for value in args[0]}
                since = args[1]
                limit = int(args[2])
                filtered = [
                    row
                    for row in self._state.activities.values()
                    if row["status"] in statuses and row["created_at"] >= since
                ]
                filtered.sort(key=lambda row: row["created_at"], reverse=True)
                return [{"payload": json.dumps(row["payload"])} for row in filtered[:limit]]

            idx = 0
            filtered = list(self._state.activities.values())
            if "repository_name =" in normalized or "lower(repository_name) = lower(" in normalized:
                repository_name = str(args[idx])
                idx += 1
                filtered = [
                    row
                    for row in filtered
                    if row["repository_name"].strip().lower() == repository_name.strip().lower()
                ]
            if "where status =" in normalized or " and status =" in normalized:
                status = str(args[idx])
                idx += 1
                filtered = [row for row in filtered if row["status"] == status]
            if "failure_type =" in normalized:
                failure_type = str(args[idx])
                idx += 1
                filtered = [row for row in filtered if row["failure_type"] == failure_type]
            if "created_at >=" in normalized:
                since = args[idx]
                idx += 1
                filtered = [row for row in filtered if row["created_at"] >= since]

            offset = int(args[idx])
            limit = int(args[idx + 1])
            filtered.sort(key=lambda row: row["created_at"], reverse=True)
            sliced = filtered[offset : offset + limit]
            return [{"payload": json.dumps(row["payload"])} for row in sliced]

        if "from ph_admin_settings_audit" in normalized:
            limit = int(args[0])
            entries = sorted(self._state.admin_audit, key=lambda item: item[0], reverse=True)
            return [{"payload": json.dumps(payload)} for _, payload in entries[:limit]]

        if "from ph_learning_queue" in normalized:
            idx = 0
            filtered = list(self._state.learning_queue.values())
            if "where status = $1" in normalized:
                status = str(args[idx])
                idx += 1
                filtered = [row for row in filtered if row["status"] == status]
            limit = int(args[idx])
            filtered.sort(key=lambda row: row["updated_at"], reverse=True)
            return [{"payload": json.dumps(row["payload"])} for row in filtered[:limit]]

        raise AssertionError(f"Unexpected fetch query: {query}")


class _FakeAcquire:
    def __init__(self, state: _FakeState) -> None:
        self._conn = _FakeConnection(state)

    async def __aenter__(self) -> _FakeConnection:
        return self._conn

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class _FakePool:
    def __init__(self, state: _FakeState) -> None:
        self._state = state
        self.closed = False

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self._state)

    async def close(self) -> None:
        self.closed = True


class _FakePoolFactory:
    def __init__(self, state: _FakeState) -> None:
        self.state = state
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> _FakePool:
        self.calls.append(kwargs)
        return _FakePool(self.state)


def _sample_activity(
    *,
    activity_id: str,
    status: RemediationStatus = RemediationStatus.PENDING,
    failure_type: FailureType | None = None,
) -> ActivityRecord:
    return ActivityRecord(
        id=activity_id,
        repositoryId="repo-1",
        repository_name="owner/repo",
        workflow_run_id=123,
        workflow_name="CI",
        status=status,
        failure_type=failure_type,
    )


async def _create_storage_for_contract(kind: str) -> InMemoryStorage | PostgresStorage:
    if kind == "memory":
        storage = InMemoryStorage()
        await storage.initialize()
        return storage
    state = _FakeState()
    storage = PostgresStorage(
        postgres_dsn="postgresql://user:pass@localhost:5432/pipelinehealer",
        pool_factory=_FakePoolFactory(state),
    )
    await storage.initialize()
    return storage


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "postgres"])
async def test_storage_contract_runtime_settings_roundtrip(
    kind: str,
) -> None:
    storage = await _create_storage_for_contract(kind)
    await storage.upsert_runtime_settings({"heal_mode": "safe", "auto_create_pr": True})
    payload = await storage.get_runtime_settings()
    assert payload == {"heal_mode": "safe", "auto_create_pr": True}
    await storage.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "postgres"])
async def test_storage_contract_activity_roundtrip(kind: str) -> None:
    storage = await _create_storage_for_contract(kind)
    activity = _sample_activity(activity_id=f"{kind}-1", status=RemediationStatus.PENDING)
    created_id = await storage.create_activity(activity)

    loaded = await storage.get_activity(created_id)
    assert loaded is not None
    loaded.status = RemediationStatus.COMPLETED
    loaded.failure_type = FailureType.DEPENDENCY
    await storage.update_activity(loaded)

    activities = await storage.get_activities(
        repository="owner/repo",
        status=RemediationStatus.COMPLETED,
        failure_type=FailureType.DEPENDENCY,
        limit=10,
    )
    assert len(activities) == 1
    assert activities[0].id == created_id
    await storage.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "postgres"])
async def test_storage_contract_repository_filter_is_case_insensitive(kind: str) -> None:
    storage = await _create_storage_for_contract(kind)
    activity = _sample_activity(activity_id=f"{kind}-case-filter")
    await storage.create_activity(activity)

    activities = await storage.get_activities(
        repository="OWNER/REPO",
        limit=10,
    )

    assert len(activities) == 1
    assert activities[0].id == f"{kind}-case-filter"
    await storage.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "postgres"])
async def test_storage_contract_learning_queue_roundtrip(kind: str) -> None:
    storage = await _create_storage_for_contract(kind)
    updated_at = utcnow().isoformat()
    await storage.upsert_learning_queue_item(
        {"id": f"{kind}-candidate", "status": "candidate", "updated_at": updated_at}
    )

    item = await storage.get_learning_queue_item(f"{kind}-candidate")
    assert item is not None
    assert item["status"] == "candidate"

    listed = await storage.list_learning_queue_items(status="candidate", limit=10)
    assert listed[0]["id"] == f"{kind}-candidate"
    await storage.close()


def test_postgres_bootstrap_sql_file_matches_runtime_fallback() -> None:
    """Guard against drift between operator SQL file and embedded fallback SQL."""
    assert _POSTGRES_BOOTSTRAP_SQL_PATH.exists()
    file_sql = _POSTGRES_BOOTSTRAP_SQL_PATH.read_text(encoding="utf-8")
    assert _q(file_sql) == _q(_POSTGRES_BOOTSTRAP_SQL)


@pytest.mark.asyncio
async def test_postgres_storage_initializes_schema_once() -> None:
    state = _FakeState()
    factory = _FakePoolFactory(state)
    storage = PostgresStorage(
        postgres_dsn="postgresql://user:pass@localhost:5432/pipelinehealer",
        pool_factory=factory,
    )

    await storage.initialize()
    await storage.initialize()

    assert len(factory.calls) == 1
    assert state.bootstrap_count == 1
    await storage.close()


@pytest.mark.asyncio
async def test_postgres_activity_crud_and_filters() -> None:
    state = _FakeState()
    storage = PostgresStorage(
        postgres_dsn="postgresql://user:pass@localhost:5432/pipelinehealer",
        pool_factory=_FakePoolFactory(state),
    )

    activity = _sample_activity(activity_id="activity-1")
    activity_id = await storage.create_activity(activity)
    assert activity_id == "activity-1"

    loaded = await storage.get_activity("activity-1")
    assert loaded is not None
    assert loaded.repository_name == "owner/repo"

    loaded.status = RemediationStatus.COMPLETED
    loaded.failure_type = FailureType.LINT
    await storage.update_activity(loaded)

    filtered = await storage.get_activities(
        repository="owner/repo",
        status=RemediationStatus.COMPLETED,
        failure_type=FailureType.LINT,
        limit=10,
        offset=0,
    )
    assert len(filtered) == 1
    assert filtered[0].id == "activity-1"
    assert filtered[0].duration_seconds is not None

    await storage.close()


@pytest.mark.asyncio
async def test_postgres_runtime_settings_audit_and_learning_queue() -> None:
    state = _FakeState()
    storage = PostgresStorage(
        postgres_dsn="postgresql://user:pass@localhost:5432/pipelinehealer",
        pool_factory=_FakePoolFactory(state),
    )

    await storage.upsert_runtime_settings({"heal_mode": "safe", "auto_create_pr": False})
    runtime = await storage.get_runtime_settings()
    assert runtime == {"heal_mode": "safe", "auto_create_pr": False}

    ts1 = datetime(2026, 3, 5, 0, 0, 0, tzinfo=UTC)
    ts2 = datetime(2026, 3, 5, 0, 0, 1, tzinfo=UTC)
    await storage.append_admin_settings_audit_entry(
        {"timestamp": ts1.isoformat(), "actor": "tester", "changed_keys": ["k1"]}
    )
    await storage.append_admin_settings_audit_entry(
        {"timestamp": ts2.isoformat(), "actor": "tester", "changed_keys": ["k2"]}
    )
    audit = await storage.list_admin_settings_audit_entries(limit=10)
    assert len(audit) == 2
    assert audit[0]["changed_keys"] == ["k2"]

    now_iso = utcnow().isoformat()
    await storage.upsert_learning_queue_item(
        {"id": "candidate-1", "status": "candidate", "updated_at": now_iso}
    )
    queue_item = await storage.get_learning_queue_item("candidate-1")
    assert queue_item is not None
    assert queue_item["status"] == "candidate"

    queue = await storage.list_learning_queue_items(status="candidate", limit=5)
    assert len(queue) == 1
    assert queue[0]["id"] == "candidate-1"

    await storage.close()


@pytest.mark.asyncio
async def test_postgres_backfill_candidates_filter_reason_code() -> None:
    state = _FakeState()
    storage = PostgresStorage(
        postgres_dsn="postgresql://user:pass@localhost:5432/pipelinehealer",
        pool_factory=_FakePoolFactory(state),
    )

    a1 = _sample_activity(
        activity_id="a1",
        status=RemediationStatus.COMPLETED,
        failure_type=FailureType.BUILD_CONFIG,
    )
    await storage.create_activity(a1)
    loaded_a1 = await storage.get_activity("a1")
    assert loaded_a1 is not None
    loaded_a1.status = RemediationStatus.COMPLETED
    loaded_a1.external_diagnostics = [
        ExternalDiagnostic(
            source="ci-doctor",
            status=ExternalDiagnosticStatus.UNAVAILABLE,
            metadata={"reason_code": "poll_window_exhausted"},
        )
    ]
    await storage.update_activity(loaded_a1)

    a2 = _sample_activity(
        activity_id="a2",
        status=RemediationStatus.COMPLETED,
        failure_type=FailureType.LINT,
    )
    await storage.create_activity(a2)
    loaded_a2 = await storage.get_activity("a2")
    assert loaded_a2 is not None
    loaded_a2.status = RemediationStatus.COMPLETED
    loaded_a2.external_diagnostics = [
        ExternalDiagnostic(
            source="ci-doctor",
            status=ExternalDiagnosticStatus.AVAILABLE,
            metadata={"reason_code": "ok"},
        )
    ]
    await storage.update_activity(loaded_a2)

    candidates = await storage.get_backfill_candidates(limit=10, max_age_hours=24.0)
    assert [candidate.id for candidate in candidates] == ["a1"]

    await storage.close()
