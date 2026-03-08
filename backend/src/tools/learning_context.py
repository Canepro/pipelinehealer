"""Deterministic retrieval of active learning artifacts for runtime context."""

from __future__ import annotations

import logging
import re
from typing import Any

from ..models import (
    Diagnosis,
    FailureContext,
    LearningContextMatch,
    LearningQueueItem,
)
from ..storage import ActivityStorage

logger = logging.getLogger(__name__)


def _normalize_reason_code(value: Any) -> str | None:
    """Normalize reason-like values into a stable lookup form."""
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or None


def extract_learning_reason_code(
    diagnosis: Diagnosis | None,
    failure_context: FailureContext | None = None,
) -> str | None:
    """Best-effort reason-code extraction for retrieval ranking."""
    details = diagnosis.error_details if diagnosis and isinstance(diagnosis.error_details, dict) else {}
    for raw in (
        details.get("reason_code"),
        details.get("classification_pattern"),
        details.get("classification_signal"),
        failure_context.signal if failure_context else None,
    ):
        normalized = _normalize_reason_code(raw)
        if normalized:
            return normalized
    return None


class LearningContextRetriever:
    """Read-only retriever that ranks active learning artifacts for one run."""

    def __init__(self, storage: ActivityStorage):
        self._storage = storage

    async def retrieve(
        self,
        *,
        repository_name: str,
        failure_type: str | None,
        reason_code: str | None = None,
        limit: int = 3,
    ) -> list[LearningContextMatch]:
        """Return the best active learning matches for the given run context."""
        normalized_failure_type = (failure_type or "").strip().lower()
        if not normalized_failure_type:
            return []

        normalized_repo = repository_name.strip().lower()
        normalized_reason_code = _normalize_reason_code(reason_code)

        rows = await self._storage.list_learning_queue_items(status="active", limit=200)
        ranked: list[LearningContextMatch] = []
        for row in rows:
            try:
                candidate = LearningQueueItem(**row)
            except Exception as exc:
                logger.warning(
                    "Skipping invalid learning queue item during runtime retrieval: id=%s error=%s",
                    row.get("id", "unknown"),
                    type(exc).__name__,
                )
                continue

            candidate_failure_type = (
                candidate.failure_type.value if candidate.failure_type is not None else ""
            ).strip().lower()
            if candidate_failure_type != normalized_failure_type:
                continue

            basis = ["failure_type exact"]
            score = 0.55

            candidate_reason_code = _normalize_reason_code(candidate.reason_code)
            if normalized_reason_code and candidate_reason_code == normalized_reason_code:
                score += 0.2
                basis.append("reason_code exact")

            candidate_repos = [repo.strip().lower() for repo in candidate.repositories if repo.strip()]
            if normalized_repo and normalized_repo in candidate_repos:
                score += 0.15
                basis.append("repository exact")

            if candidate.verification_pass_rate > 0:
                score += min(candidate.verification_pass_rate, 1.0) * 0.07
                basis.append("verification evidence")

            if candidate.occurrence_count > 0:
                score += min(candidate.occurrence_count, 5) * 0.01
                basis.append("recurrence evidence")

            ranked.append(
                LearningContextMatch(
                    id=candidate.id,
                    title=candidate.title,
                    failure_type=candidate.failure_type,
                    reason_code=candidate.reason_code,
                    suggested_playbook=candidate.suggested_playbook,
                    repositories=candidate.repositories,
                    verification_pass_rate=candidate.verification_pass_rate,
                    occurrence_count=candidate.occurrence_count,
                    match_basis=basis,
                    match_score=round(score, 4),
                )
            )

        ranked.sort(
            key=lambda item: (
                item.match_score,
                item.verification_pass_rate,
                item.occurrence_count,
                item.id,
            ),
            reverse=True,
        )
        output = ranked[: max(1, min(limit, 5))]
        for index, item in enumerate(output, start=1):
            item.match_rank = index
        return output
