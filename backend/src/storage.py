"""Storage layer for PipelineHealer using Azure Cosmos DB."""

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.identity.aio import DefaultAzureCredential

from .config import get_settings
from .models import (
    ActivityRecord,
    DashboardStats,
    FailureType,
    RemediationStatus,
)

logger = logging.getLogger(__name__)


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

        activity.created_at = datetime.utcnow()
        activity.updated_at = datetime.utcnow()

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

        activity.updated_at = datetime.utcnow()

        # Calculate duration if completed
        if (
            activity.status in (RemediationStatus.COMPLETED, RemediationStatus.FAILED)
            and activity.created_at
        ):
            delta = activity.updated_at - activity.created_at
            activity.duration_seconds = delta.total_seconds()

        item = activity.model_dump(by_alias=True, mode="json")
        item["id"] = activity.id

        await self._activities_container_required().upsert_item(body=item)
        logger.debug(f"Updated activity: {activity.id}")

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
            parameters.append({"name": "@since", "value": since.isoformat()})

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

    async def get_stats(self) -> DashboardStats:
        """Get dashboard statistics.

        Returns:
            Dashboard statistics
        """
        await self.initialize()

        # Get counts by status
        status_query = """
            SELECT c.status, COUNT(1) as count
            FROM c
            GROUP BY c.status
        """

        status_counts: dict[str, int] = {}
        async for item in self._activities_container_required().query_items(query=status_query):
            status_counts[item["status"]] = item["count"]

        # Get counts by failure type
        failure_query = """
            SELECT c.failure_type, COUNT(1) as count
            FROM c
            WHERE c.failure_type != null
            GROUP BY c.failure_type
        """

        failure_counts: dict[str, int] = {}
        async for item in self._activities_container_required().query_items(query=failure_query):
            if item.get("failure_type"):
                failure_counts[item["failure_type"]] = item["count"]

        # Get counts by repository
        repo_query = """
            SELECT c.repository_name, COUNT(1) as count
            FROM c
            GROUP BY c.repository_name
        """

        repo_counts: dict[str, int] = {}
        async for item in self._activities_container_required().query_items(query=repo_query):
            repo_counts[item["repository_name"]] = item["count"]

        # Calculate average resolution time
        avg_time_query = """
            SELECT AVG(c.duration_seconds) as avg_duration
            FROM c
            WHERE c.duration_seconds != null AND c.status = 'completed'
        """

        avg_duration = 0.0
        async for item in self._activities_container_required().query_items(query=avg_time_query):
            avg_duration = item.get("avg_duration") or 0.0

        total = sum(status_counts.values())

        return DashboardStats(
            total_runs_processed=total,
            successful_remediations=status_counts.get(RemediationStatus.COMPLETED.value, 0),
            failed_remediations=status_counts.get(RemediationStatus.FAILED.value, 0),
            pending_remediations=status_counts.get(RemediationStatus.PENDING.value, 0),
            by_failure_type=failure_counts,
            by_repository=repo_counts,
            average_resolution_time_seconds=avg_duration,
            last_updated=datetime.utcnow(),
        )

    async def get_repositories(self) -> list[dict[str, Any]]:
        """Get list of repositories with activity counts.

        Returns:
            List of repository info dictionaries
        """
        await self.initialize()

        query = """
            SELECT
                c.repository_name,
                c.repositoryId,
                COUNT(1) as total_activities,
                SUM(c.status = 'completed' ? 1 : 0) as successful,
                SUM(c.status = 'failed' ? 1 : 0) as failed
            FROM c
            GROUP BY c.repository_name, c.repositoryId
        """

        repos = [item async for item in self._activities_container_required().query_items(query=query)]

        return repos

    async def get_timeline(self, since: datetime) -> dict[str, Any]:
        """Get activity timeline data.

        Args:
            since: Start time for the timeline

        Returns:
            Timeline data for charts
        """
        await self.initialize()

        # Get activities since the specified time, grouped by day
        query = """
            SELECT
                SUBSTRING(c.created_at, 0, 10) as date,
                c.status,
                COUNT(1) as count
            FROM c
            WHERE c.created_at >= @since
            GROUP BY SUBSTRING(c.created_at, 0, 10), c.status
        """
        parameters: list[dict[str, object]] = [{"name": "@since", "value": since.isoformat()}]

        timeline_data: dict[str, dict[str, int]] = {}
        async for item in self._activities_container_required().query_items(
            query=query,
            parameters=parameters,
        ):
            date = item["date"]
            status = item["status"]
            count = item["count"]

            if date not in timeline_data:
                timeline_data[date] = {}
            timeline_data[date][status] = count

        return {
            "data": timeline_data,
            "since": since.isoformat(),
        }

    async def get_failure_breakdown(self, since: datetime) -> dict[str, int]:
        """Get failure breakdown by type.

        Args:
            since: Start time for the breakdown

        Returns:
            Dictionary of failure type to count
        """
        await self.initialize()

        query = """
            SELECT c.failure_type, COUNT(1) as count
            FROM c
            WHERE c.created_at >= @since AND c.failure_type != null
            GROUP BY c.failure_type
        """
        parameters: list[dict[str, object]] = [{"name": "@since", "value": since.isoformat()}]

        breakdown: dict[str, int] = {}
        async for item in self._activities_container_required().query_items(
            query=query,
            parameters=parameters,
        ):
            if item.get("failure_type"):
                breakdown[item["failure_type"]] = item["count"]

        return breakdown


class InMemoryStorage(ActivityStorage):
    """In-memory storage for local development and testing."""

    def __init__(self) -> None:
        """Initialize in-memory storage."""
        super().__init__()
        self._activities: dict[str, ActivityRecord] = {}
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

        activity.created_at = datetime.utcnow()
        activity.updated_at = datetime.utcnow()

        self._activities[activity.id] = activity
        logger.info(f"Created in-memory activity: {activity.id}")

        return activity.id

    async def update_activity(self, activity: ActivityRecord) -> None:
        """Update an existing activity record in memory."""
        activity.updated_at = datetime.utcnow()

        if (
            activity.status in (RemediationStatus.COMPLETED, RemediationStatus.FAILED)
            and activity.created_at
        ):
            delta = activity.updated_at - activity.created_at
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
            activities = [a for a in activities if a.repository_name == repository]

        if status:
            activities = [a for a in activities if a.status == status]

        if failure_type:
            activities = [a for a in activities if a.failure_type == failure_type]

        if since:
            activities = [a for a in activities if a.created_at and a.created_at >= since]

        # Sort by created_at descending
        activities.sort(key=lambda a: a.created_at or datetime.min, reverse=True)

        return activities[offset : offset + limit]

    async def get_stats(self) -> DashboardStats:
        """Get dashboard statistics from memory."""
        activities = list(self._activities.values())

        status_counts: dict[str, int] = {}
        failure_counts: dict[str, int] = {}
        repo_counts: dict[str, int] = {}
        total_duration = 0.0
        completed_count = 0

        for activity in activities:
            # Count by status
            status_key = activity.status.value if activity.status else "unknown"
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

            # Count by failure type
            if activity.failure_type:
                ft_key = activity.failure_type.value
                failure_counts[ft_key] = failure_counts.get(ft_key, 0) + 1

            # Count by repository
            repo_counts[activity.repository_name] = repo_counts.get(activity.repository_name, 0) + 1

            # Calculate average duration
            if activity.status == RemediationStatus.COMPLETED and activity.duration_seconds:
                total_duration += activity.duration_seconds
                completed_count += 1

        avg_duration = total_duration / completed_count if completed_count > 0 else 0.0

        return DashboardStats(
            total_runs_processed=len(activities),
            successful_remediations=status_counts.get(RemediationStatus.COMPLETED.value, 0),
            failed_remediations=status_counts.get(RemediationStatus.FAILED.value, 0),
            pending_remediations=status_counts.get(RemediationStatus.PENDING.value, 0),
            by_failure_type=failure_counts,
            by_repository=repo_counts,
            average_resolution_time_seconds=avg_duration,
            last_updated=datetime.utcnow(),
        )

    async def get_repositories(self) -> list[dict[str, Any]]:
        """Get list of repositories from memory."""
        repo_data: dict[str, dict[str, Any]] = {}

        for activity in self._activities.values():
            repo_name = activity.repository_name
            if repo_name not in repo_data:
                repo_data[repo_name] = {
                    "repository_name": repo_name,
                    "repositoryId": activity.repository_id,
                    "total_activities": 0,
                    "successful": 0,
                    "failed": 0,
                }

            repo_data[repo_name]["total_activities"] += 1
            if activity.status == RemediationStatus.COMPLETED:
                repo_data[repo_name]["successful"] += 1
            elif activity.status == RemediationStatus.FAILED:
                repo_data[repo_name]["failed"] += 1

        return list(repo_data.values())

    async def get_timeline(self, since: datetime) -> dict[str, Any]:
        """Get activity timeline data from memory."""
        timeline_data: dict[str, dict[str, int]] = {}

        for activity in self._activities.values():
            if activity.created_at and activity.created_at >= since:
                date = activity.created_at.strftime("%Y-%m-%d")
                status = activity.status.value if activity.status else "unknown"

                if date not in timeline_data:
                    timeline_data[date] = {}

                timeline_data[date][status] = timeline_data[date].get(status, 0) + 1

        return {
            "data": timeline_data,
            "since": since.isoformat(),
        }

    async def get_failure_breakdown(self, since: datetime) -> dict[str, int]:
        """Get failure breakdown from memory."""
        breakdown: dict[str, int] = {}

        for activity in self._activities.values():
            if activity.created_at and activity.created_at >= since and activity.failure_type:
                ft_key = activity.failure_type.value
                breakdown[ft_key] = breakdown.get(ft_key, 0) + 1

        return breakdown
