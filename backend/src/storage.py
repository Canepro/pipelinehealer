"""Storage layer for PipelineHealer."""

import importlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.identity.aio import DefaultAzureCredential

from .config import get_settings
from .models import (
    ActivityRecord,
    DashboardStats,
    FailureType,
    RemediationAction,
    RemediationStatus,
    utcnow,
)

logger = logging.getLogger(__name__)
_RUNTIME_SETTINGS_ID = "pipelinehealer_runtime_settings_v1"
_RUNTIME_SETTINGS_PARTITION = "__pipelinehealer_settings__"
_RUNTIME_SECRETS_PARTITION = "__pipelinehealer_runtime_secrets__"
_AUDIT_PARTITION = "__pipelinehealer_audit__"
_LEARNING_QUEUE_PARTITION = "__pipelinehealer_learning_queue__"
_POSTGRES_BOOTSTRAP_SQL_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "postgres" / "bootstrap.sql"
)
_POSTGRES_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS ph_activities (
    id TEXT PRIMARY KEY,
    repository_name TEXT NOT NULL,
    status TEXT NOT NULL,
    failure_type TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ph_activities_created_at ON ph_activities (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ph_activities_repository ON ph_activities (repository_name);
CREATE INDEX IF NOT EXISTS idx_ph_activities_status ON ph_activities (status);
CREATE INDEX IF NOT EXISTS idx_ph_activities_failure_type ON ph_activities (failure_type);

CREATE TABLE IF NOT EXISTS ph_runtime_settings (
    id TEXT PRIMARY KEY,
    updated_at TIMESTAMPTZ NOT NULL,
    settings JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS ph_runtime_secrets (
    key TEXT PRIMARY KEY,
    updated_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS ph_admin_settings_audit (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ph_admin_settings_audit_timestamp
    ON ph_admin_settings_audit (timestamp DESC);

CREATE TABLE IF NOT EXISTS ph_learning_queue (
    id TEXT PRIMARY KEY,
    status TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ph_learning_queue_updated_at
    ON ph_learning_queue (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ph_learning_queue_status
    ON ph_learning_queue (status);
"""


def _as_utc(value: datetime) -> datetime:
    """Normalize naive/aware datetimes to UTC-aware values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_datetime(value: Any) -> datetime | None:
    """Parse datetime-like values to UTC-aware datetime."""
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            return _as_utc(datetime.fromisoformat(normalized))
        except ValueError:
            return None
    return None


def _parse_json_dict(value: Any) -> dict[str, Any] | None:
    """Parse JSON-like payloads to dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def get_postgres_bootstrap_sql() -> str:
    """Return PostgreSQL bootstrap SQL used by PostgresStorage initialization.

    Prefer the checked-in SQL file so operator-facing migration docs and runtime
    initialization remain aligned. Fall back to embedded SQL for packaged
    environments where the repository scripts directory is unavailable.
    """
    if _POSTGRES_BOOTSTRAP_SQL_PATH.exists():
        return _POSTGRES_BOOTSTRAP_SQL_PATH.read_text(encoding="utf-8")
    return _POSTGRES_BOOTSTRAP_SQL


class ActivityStorage:
    """Storage for activity records using Azure Cosmos DB."""

    def _activities_container_required(self) -> ContainerProxy:
        if self._activities_container is None:
            raise RuntimeError("Storage not initialized (activities container missing)")
        return self._activities_container

    def _workflow_runs_container_required(self) -> ContainerProxy:
        if self._workflow_runs_container is None:
            raise RuntimeError("Storage not initialized (workflow_runs container missing)")
        return self._workflow_runs_container

    def __init__(
        self,
        cosmos_client: CosmosClient | None = None,
        database_name: str | None = None,
    ):
        """Initialize storage.

        Args:
            cosmos_client: Optional Cosmos DB client (for testing)
            database_name: Optional database name override
        """
        self._client = cosmos_client
        self._database_name = database_name or get_settings().cosmos_db_database
        self._activities_container: ContainerProxy | None = None
        self._workflow_runs_container: ContainerProxy | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the Cosmos DB connection."""
        if self._initialized:
            return

        settings = get_settings()

        if self._client is None:
            credential = DefaultAzureCredential()
            self._client = CosmosClient(
                settings.cosmos_db_endpoint,
                credential=credential,
            )

        database = self._client.get_database_client(self._database_name)
        self._activities_container = database.get_container_client("activities")
        self._workflow_runs_container = database.get_container_client("workflow_runs")
        self._initialized = True
        logger.info("Storage initialized successfully")

    async def close(self) -> None:
        """Close the Cosmos DB connection."""
        if self._client:
            await self._client.close()
            self._initialized = False
            self._activities_container = None
            self._workflow_runs_container = None

    async def create_activity(self, activity: ActivityRecord) -> str:
        """Create a new activity record.

        Args:
            activity: The activity record to create

        Returns:
            The ID of the created activity
        """
        await self.initialize()

        if not activity.id:
            activity.id = str(uuid4())

        activity.created_at = utcnow()
        activity.updated_at = utcnow()

        item = activity.model_dump(by_alias=True, mode="json")
        item["id"] = activity.id

        await self._activities_container_required().create_item(body=item)
        logger.info(f"Created activity: {activity.id}")

        return activity.id

    async def update_activity(self, activity: ActivityRecord) -> None:
        """Update an existing activity record.

        Args:
            activity: The activity record to update
        """
        await self.initialize()

        activity.updated_at = utcnow()

        # Calculate duration if completed
        if (
            activity.status in (RemediationStatus.COMPLETED, RemediationStatus.FAILED)
            and activity.created_at
        ):
            delta = _as_utc(activity.updated_at) - _as_utc(activity.created_at)
            activity.duration_seconds = delta.total_seconds()

        item = activity.model_dump(by_alias=True, mode="json")
        item["id"] = activity.id

        await self._activities_container_required().upsert_item(body=item)
        logger.debug(f"Updated activity: {activity.id}")

    async def upsert_runtime_settings(self, settings_payload: dict[str, Any]) -> None:
        """Persist mutable runtime settings in durable storage."""
        await self.initialize()

        item = {
            "id": _RUNTIME_SETTINGS_ID,
            "type": "runtime_settings",
            # Include common partition key candidates for compatibility with existing containers.
            "repository_name": _RUNTIME_SETTINGS_PARTITION,
            "repositoryId": _RUNTIME_SETTINGS_PARTITION,
            "repository_id": _RUNTIME_SETTINGS_PARTITION,
            "updated_at": utcnow().isoformat(),
            "settings": settings_payload,
        }
        await self._workflow_runs_container_required().upsert_item(body=item)

    async def get_runtime_settings(self) -> dict[str, Any] | None:
        """Load previously persisted mutable runtime settings from durable storage."""
        await self.initialize()

        query = "SELECT TOP 1 * FROM c WHERE c.id = @id AND c.type = @type"
        parameters: list[dict[str, object]] = [
            {"name": "@id", "value": _RUNTIME_SETTINGS_ID},
            {"name": "@type", "value": "runtime_settings"},
        ]
        items = [
            item
            async for item in self._workflow_runs_container_required().query_items(
                query=query,
                parameters=parameters,
            )
        ]
        if not items:
            return None

        settings_payload = items[0].get("settings")
        if not isinstance(settings_payload, dict):
            return None
        return settings_payload

    async def upsert_runtime_secret_record(self, secret_key: str, payload: dict[str, Any]) -> None:
        """Persist one runtime secret metadata/ciphertext record."""
        await self.initialize()

        item = {
            "id": f"runtime_secret::{secret_key}",
            "type": "runtime_secret",
            "key": secret_key,
            "repository_name": _RUNTIME_SECRETS_PARTITION,
            "repositoryId": _RUNTIME_SECRETS_PARTITION,
            "repository_id": _RUNTIME_SECRETS_PARTITION,
            "updated_at": utcnow().isoformat(),
            "payload": payload,
        }
        await self._workflow_runs_container_required().upsert_item(body=item)

    async def get_runtime_secret_record(self, secret_key: str) -> dict[str, Any] | None:
        """Load one runtime secret record by logical key."""
        await self.initialize()

        query = "SELECT TOP 1 * FROM c WHERE c.id = @id AND c.type = @type"
        parameters: list[dict[str, object]] = [
            {"name": "@id", "value": f"runtime_secret::{secret_key}"},
            {"name": "@type", "value": "runtime_secret"},
        ]
        items = [
            item
            async for item in self._workflow_runs_container_required().query_items(
                query=query,
                parameters=parameters,
            )
        ]
        if not items:
            return None

        payload = items[0].get("payload")
        if not isinstance(payload, dict):
            return None
        record = dict(payload)
        record.setdefault("updated_at", items[0].get("updated_at"))
        return record

    async def list_runtime_secret_records(self) -> dict[str, dict[str, Any]]:
        """Load all runtime secret records keyed by logical key."""
        await self.initialize()

        query = "SELECT * FROM c WHERE c.type = @type"
        parameters: list[dict[str, object]] = [{"name": "@type", "value": "runtime_secret"}]
        records: dict[str, dict[str, Any]] = {}
        async for item in self._workflow_runs_container_required().query_items(
            query=query,
            parameters=parameters,
        ):
            key = str(item.get("key") or "").strip()
            payload = item.get("payload")
            if not key or not isinstance(payload, dict):
                continue
            record = dict(payload)
            record.setdefault("updated_at", item.get("updated_at"))
            records[key] = record
        return records

    async def delete_runtime_secret_record(self, secret_key: str) -> None:
        """Delete one runtime secret metadata/ciphertext record."""
        await self.initialize()

        item_id = f"runtime_secret::{secret_key}"
        try:
            await self._workflow_runs_container_required().delete_item(
                item=item_id,
                partition_key=_RUNTIME_SECRETS_PARTITION,
            )
        except Exception:
            query = "SELECT TOP 1 * FROM c WHERE c.id = @id AND c.type = @type"
            parameters: list[dict[str, object]] = [
                {"name": "@id", "value": item_id},
                {"name": "@type", "value": "runtime_secret"},
            ]
            items = [
                item
                async for item in self._workflow_runs_container_required().query_items(
                    query=query,
                    parameters=parameters,
                )
            ]
            if items:
                await self._workflow_runs_container_required().delete_item(
                    item=item_id,
                    partition_key=items[0].get("repository_name") or _RUNTIME_SECRETS_PARTITION,
                )

    async def append_admin_settings_audit_entry(self, entry: dict[str, Any]) -> None:
        """Persist one admin settings audit entry."""
        await self.initialize()
        item = {
            "id": f"admin_settings_audit_{uuid4()}",
            "type": "admin_settings_audit",
            "repository_name": _AUDIT_PARTITION,
            "repositoryId": _AUDIT_PARTITION,
            "repository_id": _AUDIT_PARTITION,
            **entry,
        }
        await self._workflow_runs_container_required().create_item(body=item)

    async def list_admin_settings_audit_entries(self, limit: int = 50) -> list[dict[str, Any]]:
        """List persisted admin settings audit entries, newest first."""
        await self.initialize()

        safe_limit = max(1, min(limit, 200))
        query = f"""
            SELECT TOP {safe_limit} * FROM c
            WHERE c.type = @type
            ORDER BY c.timestamp DESC
        """
        parameters: list[dict[str, object]] = [{"name": "@type", "value": "admin_settings_audit"}]
        items = [
            item
            async for item in self._workflow_runs_container_required().query_items(
                query=query,
                parameters=parameters,
            )
        ]

        return items

    async def upsert_learning_queue_item(self, item: dict[str, Any]) -> None:
        """Persist one learning queue candidate item."""
        await self.initialize()

        payload = {
            "id": item.get("id"),
            "type": "learning_queue_item",
            "repository_name": _LEARNING_QUEUE_PARTITION,
            "repositoryId": _LEARNING_QUEUE_PARTITION,
            "repository_id": _LEARNING_QUEUE_PARTITION,
            **item,
        }
        await self._workflow_runs_container_required().upsert_item(body=payload)

    async def get_learning_queue_item(self, item_id: str) -> dict[str, Any] | None:
        """Load one learning queue candidate by ID."""
        await self.initialize()

        query = """
            SELECT TOP 1 * FROM c
            WHERE c.type = @type
              AND c.id = @id
        """
        parameters: list[dict[str, object]] = [
            {"name": "@type", "value": "learning_queue_item"},
            {"name": "@id", "value": item_id},
        ]
        items = [
            item
            async for item in self._workflow_runs_container_required().query_items(
                query=query,
                parameters=parameters,
            )
        ]
        if not items:
            return None
        return items[0]

    async def list_learning_queue_items(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List learning queue candidates, newest first."""
        await self.initialize()

        safe_limit = max(1, min(limit, 200))
        conditions = ["c.type = @type"]
        parameters: list[dict[str, object]] = [{"name": "@type", "value": "learning_queue_item"}]
        if status:
            conditions.append("c.status = @status")
            parameters.append({"name": "@status", "value": status})
        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT TOP {safe_limit} * FROM c
            WHERE {where_clause}
            ORDER BY c.updated_at DESC
        """
        items = [
            item
            async for item in self._workflow_runs_container_required().query_items(
                query=query,
                parameters=parameters,
            )
        ]
        return items

    async def get_activity(self, activity_id: str) -> ActivityRecord | None:
        """Get an activity record by ID.

        Args:
            activity_id: The activity ID

        Returns:
            The activity record or None if not found
        """
        await self.initialize()

        query = "SELECT * FROM c WHERE c.id = @id"
        parameters: list[dict[str, object]] = [{"name": "@id", "value": activity_id}]

        items = [
            item
            async for item in self._activities_container_required().query_items(
                query=query,
                parameters=parameters,
            )
        ]

        if not items:
            return None

        return ActivityRecord(**items[0])

    async def get_activities(
        self,
        repository: str | None = None,
        status: RemediationStatus | None = None,
        failure_type: FailureType | None = None,
        limit: int = 50,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[ActivityRecord]:
        """Get activity records with optional filtering.

        Args:
            repository: Filter by repository name
            status: Filter by status
            failure_type: Filter by failure type
            limit: Maximum number of results
            offset: Offset for pagination
            since: Filter activities since this time

        Returns:
            List of activity records
        """
        await self.initialize()

        conditions = ["1=1"]
        parameters: list[dict[str, object]] = []

        if repository:
            conditions.append("c.repository_name = @repository")
            parameters.append({"name": "@repository", "value": repository})

        if status:
            conditions.append("c.status = @status")
            parameters.append({"name": "@status", "value": status.value})

        if failure_type:
            conditions.append("c.failure_type = @failure_type")
            parameters.append({"name": "@failure_type", "value": failure_type.value})

        if since:
            conditions.append("c.created_at >= @since")
            parameters.append({"name": "@since", "value": _as_utc(since).isoformat()})

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT * FROM c
            WHERE {where_clause}
            ORDER BY c.created_at DESC
            OFFSET @offset LIMIT @limit
        """
        parameters.extend(
            [
                {"name": "@offset", "value": offset},
                {"name": "@limit", "value": limit},
            ]
        )

        items = [
            ActivityRecord(**item)
            async for item in self._activities_container_required().query_items(
                query=query,
                parameters=parameters,
            )
        ]

        return items

    async def get_backfill_candidates(
        self,
        *,
        limit: int = 20,
        max_age_hours: float = 24.0,
    ) -> list[ActivityRecord]:
        """Return completed activities whose external diagnostics need backfill.

        An activity qualifies when it is ``completed`` (or ``failed``) and has at
        least one ``ExternalDiagnostic`` entry with ``reason_code`` equal to
        ``poll_window_exhausted`` — meaning the ci-doctor findings were not
        available during the original pipeline run.

        Args:
            limit: Max candidates to return.
            max_age_hours: Only consider activities created within this many hours.

        Returns:
            List of qualifying activity records, newest first.
        """
        await self.initialize()

        since_iso = _as_utc(
            utcnow() - __import__("datetime").timedelta(hours=max_age_hours)
        ).isoformat()

        safe_limit = max(1, min(limit, 100))
        query = f"""
            SELECT TOP {safe_limit} * FROM c
            WHERE c.status IN ('completed', 'failed')
              AND c.created_at >= @since
              AND ARRAY_LENGTH(c.external_diagnostics) > 0
            ORDER BY c.created_at DESC
        """
        parameters: list[dict[str, object]] = [{"name": "@since", "value": since_iso}]

        candidates: list[ActivityRecord] = []
        async for item in self._activities_container_required().query_items(
            query=query,
            parameters=parameters,
        ):
            activity = ActivityRecord(**item)
            # Filter in Python: at least one diagnostic with poll_window_exhausted
            if any(
                d.metadata.get("reason_code") == "poll_window_exhausted"
                for d in activity.external_diagnostics
            ):
                candidates.append(activity)
        return candidates

    async def get_stats(self) -> DashboardStats:
        """Get dashboard statistics.

        Returns:
            Dashboard statistics
        """
        status_counts: dict[str, int] = {}
        failure_counts: dict[str, int] = {}
        repo_counts: dict[str, int] = {}
        total_duration = 0.0
        completed_with_duration = 0
        actioned_remediations = 0
        auto_pr_remediations = 0
        issue_remediations = 0
        safety_blocked_remediations = 0
        thirty_day_cutoff = _as_utc(utcnow() - timedelta(days=30))
        mcp_enabled_runs_30d = 0
        llm_observed_runs_30d = 0
        llm_fallback_runs_30d = 0

        async for activity in self._iter_activities():
            status_key = activity.status.value if activity.status else "unknown"
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

            if activity.failure_type:
                failure_key = activity.failure_type.value
                failure_counts[failure_key] = failure_counts.get(failure_key, 0) + 1

            if activity.repository_name:
                repo_counts[activity.repository_name] = repo_counts.get(activity.repository_name, 0) + 1

            if (
                activity.status == RemediationStatus.COMPLETED
                and isinstance(activity.duration_seconds, (int, float))
            ):
                total_duration += float(activity.duration_seconds)
                completed_with_duration += 1

            remediation = activity.remediation_result
            if (
                activity.status == RemediationStatus.COMPLETED
                and remediation
                and remediation.success
                and remediation.action_taken in {
                    RemediationAction.CREATE_PR,
                    RemediationAction.CREATE_ISSUE,
                    RemediationAction.RETRY_WORKFLOW,
                }
            ):
                actioned_remediations += 1
                if remediation.action_taken == RemediationAction.CREATE_PR:
                    auto_pr_remediations += 1
                elif remediation.action_taken == RemediationAction.CREATE_ISSUE:
                    issue_remediations += 1

                details = remediation.details or {}
                if (
                    isinstance(details.get("not_auto_reason_code"), str)
                    or details.get("fallback_from") == "create_pr"
                ):
                    safety_blocked_remediations += 1

            created_at = _as_utc(activity.created_at) if activity.created_at else None
            if created_at and created_at >= thirty_day_cutoff:
                if activity.mcp_model_path and activity.mcp_model_path.enabled:
                    mcp_enabled_runs_30d += 1
                if activity.llm_model_path and activity.llm_model_path.call_count > 0:
                    llm_observed_runs_30d += 1
                    if activity.llm_model_path.fallback_used:
                        llm_fallback_runs_30d += 1

        total = sum(status_counts.values())
        avg_duration = total_duration / completed_with_duration if completed_with_duration > 0 else 0.0
        llm_fallback_rate_30d = (
            (llm_fallback_runs_30d / llm_observed_runs_30d) * 100.0
            if llm_observed_runs_30d > 0
            else 0.0
        )

        return DashboardStats(
            total_runs_processed=total,
            actioned_remediations=actioned_remediations,
            successful_remediations=actioned_remediations,
            failed_remediations=status_counts.get(RemediationStatus.FAILED.value, 0),
            pending_remediations=status_counts.get(RemediationStatus.PENDING.value, 0),
            auto_pr_remediations=auto_pr_remediations,
            issue_remediations=issue_remediations,
            safety_blocked_remediations=safety_blocked_remediations,
            mcp_enabled_runs_30d=mcp_enabled_runs_30d,
            llm_fallback_rate_30d=round(llm_fallback_rate_30d, 2),
            by_failure_type=failure_counts,
            by_repository=repo_counts,
            average_resolution_time_seconds=avg_duration,
            last_updated=utcnow(),
        )

    async def get_repositories(self) -> list[dict[str, Any]]:
        """Get list of repositories with activity counts.

        Returns:
            List of repository info dictionaries
        """
        repos_by_name: dict[str, dict[str, Any]] = {}

        async for activity in self._iter_activities():
            repo_name = activity.repository_name
            if not repo_name:
                continue

            if repo_name not in repos_by_name:
                repos_by_name[repo_name] = {
                    "repository_name": repo_name,
                    "repositoryId": activity.repository_id,
                    "total_activities": 0,
                    "successful": 0,
                    "failed": 0,
                }

            repos_by_name[repo_name]["total_activities"] += 1
            if activity.status == RemediationStatus.COMPLETED:
                repos_by_name[repo_name]["successful"] += 1
            elif activity.status == RemediationStatus.FAILED:
                repos_by_name[repo_name]["failed"] += 1

        return list(repos_by_name.values())

    async def get_timeline(self, since: datetime) -> dict[str, Any]:
        """Get activity timeline data.

        Args:
            since: Start time for the timeline

        Returns:
            Timeline data for charts
        """
        timeline_data: dict[str, dict[str, int]] = {}

        async for activity in self._iter_activities(since=since):
            if not activity.created_at:
                continue
            date = _as_utc(activity.created_at).strftime("%Y-%m-%d")
            status = activity.status.value if activity.status else "unknown"

            if date not in timeline_data:
                timeline_data[date] = {}
            timeline_data[date][status] = timeline_data[date].get(status, 0) + 1

        return {
            "data": timeline_data,
            "since": _as_utc(since).isoformat(),
        }

    async def get_failure_breakdown(self, since: datetime) -> dict[str, int]:
        """Get failure breakdown by type.

        Args:
            since: Start time for the breakdown

        Returns:
            Dictionary of failure type to count
        """
        breakdown: dict[str, int] = {}
        async for activity in self._iter_activities(since=since):
            if activity.failure_type:
                failure_key = activity.failure_type.value
                breakdown[failure_key] = breakdown.get(failure_key, 0) + 1

        return breakdown

    async def iter_activities(
        self,
        *,
        since: datetime | None = None,
        page_size: int = 200,
    ) -> AsyncIterator[ActivityRecord]:
        """Yield activities using the adapter's efficient paging strategy."""
        async for activity in self._iter_activities(since=since, page_size=page_size):
            yield activity

    async def _iter_activities(
        self,
        *,
        since: datetime | None = None,
        page_size: int = 200,
    ) -> AsyncIterator[ActivityRecord]:
        """Yield activities using Cosmos SDK continuation-token paging.

        Unlike the OFFSET/LIMIT fallback (used by InMemoryStorage), this
        iterates the ``query_items`` async pager directly so the SDK handles
        continuation tokens internally — avoiding the O(n*pages) cost of
        repeated OFFSET queries on large collections.
        """
        await self.initialize()

        conditions = ["1=1"]
        parameters: list[dict[str, object]] = []

        if since:
            conditions.append("c.created_at >= @since")
            parameters.append({"name": "@since", "value": _as_utc(since).isoformat()})

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT * FROM c
            WHERE {where_clause}
            ORDER BY c.created_at DESC
        """

        async for item in self._activities_container_required().query_items(
            query=query,
            parameters=parameters,
            max_item_count=page_size,
        ):
            yield ActivityRecord(**item)


class PostgresStorage(ActivityStorage):
    """PostgreSQL-backed storage adapter."""

    def __init__(
        self,
        postgres_dsn: str | None = None,
        pool_factory: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        """Initialize PostgreSQL storage.

        Args:
            postgres_dsn: Optional PostgreSQL DSN override.
            pool_factory: Optional async pool factory for testing.
        """
        super().__init__()
        self._postgres_dsn = postgres_dsn or get_settings().postgres_dsn
        self._pool_factory = pool_factory
        self._pool: Any | None = None

    def _pool_required(self) -> Any:
        if self._pool is None:
            raise RuntimeError("Storage not initialized (postgres pool missing)")
        return self._pool

    async def initialize(self) -> None:
        """Initialize PostgreSQL pool and bootstrap schema."""
        if self._initialized:
            return

        dsn = str(self._postgres_dsn).strip()
        if not dsn:
            raise RuntimeError("STORAGE_MODE=postgres requires POSTGRES_DSN")

        if self._pool_factory is None:
            try:
                asyncpg = importlib.import_module("asyncpg")
            except ImportError as exc:
                raise RuntimeError(
                    "PostgreSQL storage requires asyncpg. Install backend dependencies first."
                ) from exc
            self._pool_factory = asyncpg.create_pool

        self._pool = await self._pool_factory(dsn=dsn, min_size=1, max_size=5)
        async with self._pool_required().acquire() as conn:
            await conn.execute(get_postgres_bootstrap_sql())
        self._initialized = True
        logger.info("PostgreSQL storage initialized successfully")

    async def close(self) -> None:
        """Close PostgreSQL pool."""
        if self._pool is not None:
            await self._pool.close()
        self._pool = None
        self._initialized = False

    async def create_activity(self, activity: ActivityRecord) -> str:
        """Create a new activity record."""
        await self.initialize()

        if not activity.id:
            activity.id = str(uuid4())

        activity.created_at = utcnow()
        activity.updated_at = utcnow()

        payload = activity.model_dump(by_alias=True, mode="json")
        payload["id"] = activity.id
        status = activity.status.value if activity.status else "unknown"
        failure_type = activity.failure_type.value if activity.failure_type else None

        async with self._pool_required().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ph_activities (
                    id, repository_name, status, failure_type, created_at, updated_at, payload
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                activity.id,
                activity.repository_name,
                status,
                failure_type,
                _as_utc(activity.created_at),
                _as_utc(activity.updated_at),
                json.dumps(payload),
            )
        logger.info("Created postgres activity: %s", activity.id)
        return activity.id

    async def update_activity(self, activity: ActivityRecord) -> None:
        """Update an existing activity record."""
        await self.initialize()

        activity.updated_at = utcnow()
        if (
            activity.status in (RemediationStatus.COMPLETED, RemediationStatus.FAILED)
            and activity.created_at
        ):
            delta = _as_utc(activity.updated_at) - _as_utc(activity.created_at)
            activity.duration_seconds = delta.total_seconds()

        payload = activity.model_dump(by_alias=True, mode="json")
        payload["id"] = activity.id
        status = activity.status.value if activity.status else "unknown"
        failure_type = activity.failure_type.value if activity.failure_type else None
        created_at = _as_utc(activity.created_at) if activity.created_at else _as_utc(utcnow())

        async with self._pool_required().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ph_activities (
                    id, repository_name, status, failure_type, created_at, updated_at, payload
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    repository_name = EXCLUDED.repository_name,
                    status = EXCLUDED.status,
                    failure_type = EXCLUDED.failure_type,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at,
                    payload = EXCLUDED.payload
                """,
                activity.id,
                activity.repository_name,
                status,
                failure_type,
                created_at,
                _as_utc(activity.updated_at),
                json.dumps(payload),
            )
        logger.debug("Updated postgres activity: %s", activity.id)

    async def get_activity(self, activity_id: str) -> ActivityRecord | None:
        """Get one activity by ID."""
        await self.initialize()
        async with self._pool_required().acquire() as conn:
            row = await conn.fetchrow(
                "SELECT payload::text AS payload FROM ph_activities WHERE id = $1",
                activity_id,
            )
        if row is None:
            return None
        payload = _parse_json_dict(row["payload"])
        if payload is None:
            return None
        return ActivityRecord(**payload)

    async def get_activities(
        self,
        repository: str | None = None,
        status: RemediationStatus | None = None,
        failure_type: FailureType | None = None,
        limit: int = 50,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[ActivityRecord]:
        """Get activities with optional filters."""
        await self.initialize()

        safe_limit = max(1, min(limit, 500))
        safe_offset = max(0, offset)
        args: list[Any] = []
        conditions: list[str] = []

        if repository:
            args.append(repository.strip())
            conditions.append(f"LOWER(repository_name) = LOWER(${len(args)})")
        if status:
            args.append(status.value)
            conditions.append(f"status = ${len(args)}")
        if failure_type:
            args.append(failure_type.value)
            conditions.append(f"failure_type = ${len(args)}")
        if since:
            args.append(_as_utc(since))
            conditions.append(f"created_at >= ${len(args)}")

        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        args.append(safe_offset)
        args.append(safe_limit)
        query = f"""
            SELECT payload::text AS payload
            FROM ph_activities
            WHERE {where_clause}
            ORDER BY created_at DESC
            OFFSET ${len(args) - 1}
            LIMIT ${len(args)}
        """

        async with self._pool_required().acquire() as conn:
            rows = await conn.fetch(query, *args)

        items: list[ActivityRecord] = []
        for row in rows:
            payload = _parse_json_dict(row["payload"])
            if payload is None:
                continue
            items.append(ActivityRecord(**payload))
        return items

    async def get_backfill_candidates(
        self,
        *,
        limit: int = 20,
        max_age_hours: float = 24.0,
    ) -> list[ActivityRecord]:
        """Return completed activities whose diagnostics need backfill."""
        await self.initialize()

        safe_limit = max(1, min(limit, 100))
        fetch_limit = max(safe_limit, min(safe_limit * 5, 500))
        since = _as_utc(utcnow() - timedelta(hours=max_age_hours))

        async with self._pool_required().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT payload::text AS payload
                FROM ph_activities
                WHERE status = ANY($1::text[])
                  AND created_at >= $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                [
                    RemediationStatus.COMPLETED.value,
                    RemediationStatus.FAILED.value,
                ],
                since,
                fetch_limit,
            )

        candidates: list[ActivityRecord] = []
        for row in rows:
            payload = _parse_json_dict(row["payload"])
            if payload is None:
                continue
            activity = ActivityRecord(**payload)
            if any(
                diagnostic.metadata.get("reason_code") == "poll_window_exhausted"
                for diagnostic in activity.external_diagnostics
            ):
                candidates.append(activity)
                if len(candidates) >= safe_limit:
                    break
        return candidates

    async def upsert_runtime_settings(self, settings_payload: dict[str, Any]) -> None:
        """Persist mutable runtime settings."""
        await self.initialize()

        async with self._pool_required().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ph_runtime_settings (id, updated_at, settings)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    updated_at = EXCLUDED.updated_at,
                    settings = EXCLUDED.settings
                """,
                _RUNTIME_SETTINGS_ID,
                utcnow(),
                json.dumps(settings_payload),
            )

    async def get_runtime_settings(self) -> dict[str, Any] | None:
        """Load mutable runtime settings from storage."""
        await self.initialize()

        async with self._pool_required().acquire() as conn:
            row = await conn.fetchrow(
                "SELECT settings::text AS settings FROM ph_runtime_settings WHERE id = $1",
                _RUNTIME_SETTINGS_ID,
            )
        if row is None:
            return None
        payload = _parse_json_dict(row["settings"])
        if payload is None:
            return None
        return payload

    async def upsert_runtime_secret_record(self, secret_key: str, payload: dict[str, Any]) -> None:
        """Persist one runtime secret metadata/ciphertext record."""
        await self.initialize()

        async with self._pool_required().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ph_runtime_secrets (key, updated_at, payload)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (key) DO UPDATE SET
                    updated_at = EXCLUDED.updated_at,
                    payload = EXCLUDED.payload
                """,
                secret_key,
                utcnow(),
                json.dumps(payload),
            )

    async def get_runtime_secret_record(self, secret_key: str) -> dict[str, Any] | None:
        """Load one runtime secret record by logical key."""
        await self.initialize()

        async with self._pool_required().acquire() as conn:
            row = await conn.fetchrow(
                "SELECT updated_at, payload::text AS payload FROM ph_runtime_secrets WHERE key = $1",
                secret_key,
            )
        if row is None:
            return None
        payload = _parse_json_dict(row["payload"])
        if payload is None:
            return None
        payload["updated_at"] = _as_utc(row["updated_at"]).isoformat()
        return payload

    async def list_runtime_secret_records(self) -> dict[str, dict[str, Any]]:
        """Load all runtime secret records keyed by logical key."""
        await self.initialize()

        async with self._pool_required().acquire() as conn:
            rows = await conn.fetch(
                "SELECT key, updated_at, payload::text AS payload FROM ph_runtime_secrets"
            )
        records: dict[str, dict[str, Any]] = {}
        for row in rows:
            payload = _parse_json_dict(row["payload"])
            if payload is None:
                continue
            payload["updated_at"] = _as_utc(row["updated_at"]).isoformat()
            records[str(row["key"])] = payload
        return records

    async def delete_runtime_secret_record(self, secret_key: str) -> None:
        """Delete one runtime secret record by logical key."""
        await self.initialize()

        async with self._pool_required().acquire() as conn:
            await conn.execute("DELETE FROM ph_runtime_secrets WHERE key = $1", secret_key)

    async def append_admin_settings_audit_entry(self, entry: dict[str, Any]) -> None:
        """Persist one admin settings audit entry."""
        await self.initialize()

        payload = dict(entry)
        timestamp = _parse_datetime(payload.get("timestamp")) or utcnow()
        async with self._pool_required().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ph_admin_settings_audit (timestamp, payload)
                VALUES ($1, $2::jsonb)
                """,
                timestamp,
                json.dumps(payload),
            )

    async def list_admin_settings_audit_entries(self, limit: int = 50) -> list[dict[str, Any]]:
        """List admin settings audit entries, newest first."""
        await self.initialize()

        safe_limit = max(1, min(limit, 200))
        async with self._pool_required().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT payload::text AS payload
                FROM ph_admin_settings_audit
                ORDER BY timestamp DESC
                LIMIT $1
                """,
                safe_limit,
            )
        entries: list[dict[str, Any]] = []
        for row in rows:
            payload = _parse_json_dict(row["payload"])
            if payload is None:
                continue
            entries.append(payload)
        return entries

    async def upsert_learning_queue_item(self, item: dict[str, Any]) -> None:
        """Persist one learning queue item."""
        await self.initialize()

        item_id = str(item.get("id", "")).strip()
        if not item_id:
            raise ValueError("Learning queue item must include a non-empty id")

        payload = dict(item)
        status = str(payload.get("status", "")).strip().lower() or None
        updated_at = _parse_datetime(payload.get("updated_at")) or utcnow()
        async with self._pool_required().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ph_learning_queue (id, status, updated_at, payload)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at,
                    payload = EXCLUDED.payload
                """,
                item_id,
                status,
                updated_at,
                json.dumps(payload),
            )

    async def get_learning_queue_item(self, item_id: str) -> dict[str, Any] | None:
        """Load one learning queue item by ID."""
        await self.initialize()

        async with self._pool_required().acquire() as conn:
            row = await conn.fetchrow(
                "SELECT payload::text AS payload FROM ph_learning_queue WHERE id = $1",
                item_id,
            )
        if row is None:
            return None
        payload = _parse_json_dict(row["payload"])
        if payload is None:
            return None
        return payload

    async def list_learning_queue_items(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List learning queue items, newest first."""
        await self.initialize()

        safe_limit = max(1, min(limit, 200))
        normalized_status = status.strip().lower() if status else None
        async with self._pool_required().acquire() as conn:
            if normalized_status:
                rows = await conn.fetch(
                    """
                    SELECT payload::text AS payload
                    FROM ph_learning_queue
                    WHERE status = $1
                    ORDER BY updated_at DESC
                    LIMIT $2
                    """,
                    normalized_status,
                    safe_limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT payload::text AS payload
                    FROM ph_learning_queue
                    ORDER BY updated_at DESC
                    LIMIT $1
                    """,
                    safe_limit,
                )
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = _parse_json_dict(row["payload"])
            if payload is None:
                continue
            items.append(payload)
        return items

    async def _iter_activities(
        self,
        *,
        since: datetime | None = None,
        page_size: int = 200,
    ) -> AsyncIterator[ActivityRecord]:
        """Yield activities via keyset pagination to avoid large OFFSET scans."""
        await self.initialize()

        safe_page_size = max(1, min(page_size, 500))
        cursor_created_at: datetime | None = None
        cursor_id: str | None = None
        while True:
            args: list[Any] = []
            conditions: list[str] = []
            if since:
                args.append(_as_utc(since))
                conditions.append(f"created_at >= ${len(args)}")
            if cursor_created_at is not None and cursor_id is not None:
                args.append(cursor_created_at)
                created_idx = len(args)
                args.append(cursor_id)
                id_idx = len(args)
                conditions.append(
                    f"(created_at < ${created_idx} OR (created_at = ${created_idx} AND id < ${id_idx}))"
                )

            where_clause = " AND ".join(conditions) if conditions else "TRUE"
            args.append(safe_page_size)
            query = f"""
                SELECT id, created_at, payload::text AS payload
                FROM ph_activities
                WHERE {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT ${len(args)}
            """
            async with self._pool_required().acquire() as conn:
                rows = await conn.fetch(query, *args)
            if not rows:
                break
            count = 0
            for row in rows:
                payload = _parse_json_dict(row["payload"])
                if payload is None:
                    continue
                count += 1
                yield ActivityRecord(**payload)
            if count == 0 or count < safe_page_size:
                break
            last_row = rows[-1]
            cursor_created_at = _as_utc(last_row["created_at"])
            cursor_id = str(last_row["id"])


class InMemoryStorage(ActivityStorage):
    """In-memory storage for local development and testing."""

    def __init__(self) -> None:
        """Initialize in-memory storage."""
        super().__init__()
        self._activities: dict[str, ActivityRecord] = {}
        self._runtime_settings: dict[str, Any] | None = None
        self._runtime_secrets: dict[str, dict[str, Any]] = {}
        self._admin_settings_audit: list[dict[str, Any]] = []
        self._learning_queue_items: dict[str, dict[str, Any]] = {}
        self._initialized = True

    async def initialize(self) -> None:
        """No-op for in-memory storage."""
        pass

    async def close(self) -> None:
        """No-op for in-memory storage."""
        pass

    async def create_activity(self, activity: ActivityRecord) -> str:
        """Create a new activity record in memory."""
        if not activity.id:
            activity.id = str(uuid4())

        activity.created_at = utcnow()
        activity.updated_at = utcnow()

        self._activities[activity.id] = activity
        logger.info(f"Created in-memory activity: {activity.id}")

        return activity.id

    async def update_activity(self, activity: ActivityRecord) -> None:
        """Update an existing activity record in memory."""
        activity.updated_at = utcnow()

        if (
            activity.status in (RemediationStatus.COMPLETED, RemediationStatus.FAILED)
            and activity.created_at
        ):
            delta = _as_utc(activity.updated_at) - _as_utc(activity.created_at)
            activity.duration_seconds = delta.total_seconds()

        self._activities[activity.id] = activity
        logger.debug(f"Updated in-memory activity: {activity.id}")

    async def get_activity(self, activity_id: str) -> ActivityRecord | None:
        """Get an activity record by ID from memory."""
        return self._activities.get(activity_id)

    async def get_activities(
        self,
        repository: str | None = None,
        status: RemediationStatus | None = None,
        failure_type: FailureType | None = None,
        limit: int = 50,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[ActivityRecord]:
        """Get activity records with optional filtering from memory."""
        activities = list(self._activities.values())

        if repository:
            repository_filter = repository.strip().lower()
            activities = [
                a for a in activities if a.repository_name.strip().lower() == repository_filter
            ]

        if status:
            activities = [a for a in activities if a.status == status]

        if failure_type:
            activities = [a for a in activities if a.failure_type == failure_type]

        if since:
            since_utc = _as_utc(since)
            activities = [a for a in activities if a.created_at and _as_utc(a.created_at) >= since_utc]

        # Sort by created_at descending
        activities.sort(
            key=lambda a: _as_utc(a.created_at).timestamp() if a.created_at else float("-inf"),
            reverse=True,
        )

        return activities[offset : offset + limit]

    async def _iter_activities(
        self,
        *,
        since: datetime | None = None,
        page_size: int = 200,
    ) -> AsyncIterator[ActivityRecord]:
        """Yield in-memory activities via simple offset paging."""
        offset = 0
        while True:
            page = await self.get_activities(limit=page_size, offset=offset, since=since)
            if not page:
                break
            for activity in page:
                yield activity
            if len(page) < page_size:
                break
            offset += len(page)

    async def get_backfill_candidates(
        self,
        *,
        limit: int = 20,
        max_age_hours: float = 24.0,
    ) -> list[ActivityRecord]:
        """Return in-memory activities needing external diagnostics backfill."""
        from datetime import timedelta

        cutoff = _as_utc(utcnow() - timedelta(hours=max_age_hours))
        candidates: list[ActivityRecord] = []
        for activity in self._activities.values():
            if activity.status not in (RemediationStatus.COMPLETED, RemediationStatus.FAILED):
                continue
            if activity.created_at and _as_utc(activity.created_at) < cutoff:
                continue
            if any(
                d.metadata.get("reason_code") == "poll_window_exhausted"
                for d in activity.external_diagnostics
            ):
                candidates.append(activity)
        candidates.sort(
            key=lambda a: _as_utc(a.created_at).timestamp() if a.created_at else 0,
            reverse=True,
        )
        return candidates[:limit]

    async def upsert_runtime_settings(self, settings_payload: dict[str, Any]) -> None:
        """Persist runtime settings in-memory (test/local fallback)."""
        self._runtime_settings = dict(settings_payload)

    async def get_runtime_settings(self) -> dict[str, Any] | None:
        """Return last persisted runtime settings from memory."""
        if self._runtime_settings is None:
            return None
        return dict(self._runtime_settings)

    async def upsert_runtime_secret_record(self, secret_key: str, payload: dict[str, Any]) -> None:
        """Persist one runtime secret record in-memory."""
        record = dict(payload)
        record["updated_at"] = utcnow().isoformat()
        self._runtime_secrets[secret_key] = record

    async def get_runtime_secret_record(self, secret_key: str) -> dict[str, Any] | None:
        """Return one in-memory runtime secret record."""
        record = self._runtime_secrets.get(secret_key)
        return dict(record) if record is not None else None

    async def list_runtime_secret_records(self) -> dict[str, dict[str, Any]]:
        """Return all in-memory runtime secret records."""
        return {key: dict(value) for key, value in self._runtime_secrets.items()}

    async def delete_runtime_secret_record(self, secret_key: str) -> None:
        """Delete one in-memory runtime secret record."""
        self._runtime_secrets.pop(secret_key, None)

    async def append_admin_settings_audit_entry(self, entry: dict[str, Any]) -> None:
        """Persist one admin settings audit entry in-memory."""
        self._admin_settings_audit.append(dict(entry))

    async def list_admin_settings_audit_entries(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return in-memory admin settings audit entries, newest first."""
        safe_limit = max(1, min(limit, 200))
        return [dict(item) for item in reversed(self._admin_settings_audit)][
            :safe_limit
        ]

    async def upsert_learning_queue_item(self, item: dict[str, Any]) -> None:
        """Persist one learning queue candidate in-memory."""
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            raise ValueError("Learning queue item must include a non-empty id")
        self._learning_queue_items[item_id] = dict(item)

    async def get_learning_queue_item(self, item_id: str) -> dict[str, Any] | None:
        """Load one in-memory learning queue item by ID."""
        item = self._learning_queue_items.get(item_id)
        if item is None:
            return None
        return dict(item)

    async def list_learning_queue_items(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List in-memory learning queue items, newest first."""
        safe_limit = max(1, min(limit, 200))
        items = list(self._learning_queue_items.values())
        if status:
            items = [item for item in items if str(item.get("status", "")).lower() == status.lower()]
        items.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return [dict(item) for item in items[:safe_limit]]
