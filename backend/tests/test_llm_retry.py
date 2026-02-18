"""Tests for LLM transient-error retry logic in agents/base.py."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.base import (
    FallbackAgent,
    _is_retryable_llm_error,
    _run_with_llm_retry,
)

# ---------------------------------------------------------------------------
# _is_retryable_llm_error
# ---------------------------------------------------------------------------


class TestIsRetryableLlmError:
    def test_retryable_builtin_timeout_without_message(self) -> None:
        assert _is_retryable_llm_error(TimeoutError()) is True

    def test_retryable_status_code_attribute(self) -> None:
        class _StatusCodeError(Exception):
            def __init__(self, status_code: int) -> None:
                super().__init__("status error")
                self.status_code = status_code

        assert _is_retryable_llm_error(_StatusCodeError(503)) is True

    def test_retryable_response_status_attribute(self) -> None:
        class _Response:
            def __init__(self, status_code: int) -> None:
                self.status_code = status_code

        class _ResponseError(Exception):
            def __init__(self, status_code: int) -> None:
                super().__init__("response error")
                self.response = _Response(status_code)

        assert _is_retryable_llm_error(_ResponseError(429)) is True

    def test_429_status_code(self) -> None:
        assert _is_retryable_llm_error(Exception("HTTP 429 Too Many Requests")) is True

    def test_500_status_code(self) -> None:
        assert _is_retryable_llm_error(Exception("HTTP 500 Internal Server Error")) is True

    def test_502_status_code(self) -> None:
        assert _is_retryable_llm_error(Exception("502 Bad Gateway")) is True

    def test_503_status_code(self) -> None:
        assert _is_retryable_llm_error(Exception("Service Unavailable 503")) is True

    def test_rate_limit_phrase(self) -> None:
        assert _is_retryable_llm_error(Exception("Rate limit exceeded")) is True

    def test_too_many_requests_phrase(self) -> None:
        assert _is_retryable_llm_error(Exception("too many requests")) is True

    def test_temporarily_unavailable(self) -> None:
        assert _is_retryable_llm_error(Exception("Service temporarily unavailable")) is True

    def test_connection_error(self) -> None:
        assert _is_retryable_llm_error(Exception("connection error: reset by peer")) is True

    def test_timeout_phrase(self) -> None:
        assert _is_retryable_llm_error(Exception("request timeout")) is True

    def test_non_retryable_auth_error(self) -> None:
        assert _is_retryable_llm_error(Exception("401 Unauthorized")) is False

    def test_non_retryable_validation_error(self) -> None:
        assert _is_retryable_llm_error(Exception("Invalid prompt format")) is False

    def test_non_retryable_api_version(self) -> None:
        assert _is_retryable_llm_error(Exception("API version not supported")) is False


# ---------------------------------------------------------------------------
# _run_with_llm_retry
# ---------------------------------------------------------------------------


class TestRunWithLlmRetry:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self) -> None:
        agent = AsyncMock()
        agent.run.return_value = "ok"

        result = await _run_with_llm_retry(agent, "hello")

        assert result == "ok"
        assert agent.run.call_count == 1

    @pytest.mark.asyncio
    @patch("src.agents.base.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_on_429_then_succeeds(self, mock_sleep: AsyncMock) -> None:
        agent = AsyncMock()
        agent.run.side_effect = [
            Exception("HTTP 429 Too Many Requests"),
            "recovered",
        ]

        result = await _run_with_llm_retry(agent, "hello")

        assert result == "recovered"
        assert agent.run.call_count == 2
        assert mock_sleep.call_count == 1

    @pytest.mark.asyncio
    @patch("src.agents.base.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_on_5xx_then_succeeds(self, mock_sleep: AsyncMock) -> None:
        agent = AsyncMock()
        agent.run.side_effect = [
            Exception("502 Bad Gateway"),
            Exception("503 Service Unavailable"),
            "recovered",
        ]

        result = await _run_with_llm_retry(agent, "hello")

        assert result == "recovered"
        assert agent.run.call_count == 3
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    @patch("src.agents.base.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_on_timeout_exception_without_message(self, mock_sleep: AsyncMock) -> None:
        agent = AsyncMock()
        agent.run.side_effect = [TimeoutError(), "recovered"]

        result = await _run_with_llm_retry(agent, "hello")

        assert result == "recovered"
        assert agent.run.call_count == 2
        assert mock_sleep.call_count == 1

    @pytest.mark.asyncio
    @patch("src.agents.base.asyncio.sleep", new_callable=AsyncMock)
    async def test_raises_after_max_retries_exhausted(self, mock_sleep: AsyncMock) -> None:
        agent = AsyncMock()
        agent.run.side_effect = Exception("HTTP 429 Too Many Requests")

        with pytest.raises(Exception, match="429"):
            await _run_with_llm_retry(agent, "hello")

        # 1 initial + 3 retries = 4 total attempts
        assert agent.run.call_count == 4
        assert mock_sleep.call_count == 3

    @pytest.mark.asyncio
    async def test_does_not_retry_non_retryable_error(self) -> None:
        agent = AsyncMock()
        agent.run.side_effect = ValueError("Invalid prompt format")

        with pytest.raises(ValueError, match="Invalid prompt"):
            await _run_with_llm_retry(agent, "hello")

        assert agent.run.call_count == 1

    @pytest.mark.asyncio
    @patch("src.agents.base.asyncio.sleep", new_callable=AsyncMock)
    async def test_backoff_delays_increase(self, mock_sleep: AsyncMock) -> None:
        agent = AsyncMock()
        agent.run.side_effect = [
            Exception("HTTP 429"),
            Exception("HTTP 429"),
            Exception("HTTP 429"),
            "ok",
        ]

        # Pin random jitter to 0 for deterministic delay assertions.
        with patch("src.agents.base.random.uniform", return_value=0.0):
            await _run_with_llm_retry(agent, "hello")

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        # base=1.0 → 1*2^0=1.0, 1*2^1=2.0, 1*2^2=4.0
        assert delays == [1.0, 2.0, 4.0]


# ---------------------------------------------------------------------------
# FallbackAgent integration with retry
# ---------------------------------------------------------------------------


class TestFallbackAgentRetry:
    def setup_method(self) -> None:
        FallbackAgent._primary_failed = False

    @pytest.mark.asyncio
    @patch("src.agents.base.asyncio.sleep", new_callable=AsyncMock)
    async def test_primary_retries_transient_then_succeeds(self, mock_sleep: AsyncMock) -> None:
        primary = AsyncMock()
        primary.run.side_effect = [Exception("HTTP 429"), "primary ok"]
        fallback = AsyncMock()

        agent = FallbackAgent(primary, fallback)
        result = await agent.run("hello")

        assert result == "primary ok"
        assert primary.run.call_count == 2
        assert fallback.run.call_count == 0

    @pytest.mark.asyncio
    async def test_api_version_error_switches_to_fallback(self) -> None:
        primary = AsyncMock()
        primary.run.side_effect = Exception("API version not supported")
        fallback = AsyncMock()
        fallback.run.return_value = "fallback ok"

        agent = FallbackAgent(primary, fallback)
        result = await agent.run("hello")

        assert result == "fallback ok"
        assert FallbackAgent._primary_failed is True

    @pytest.mark.asyncio
    @patch("src.agents.base.asyncio.sleep", new_callable=AsyncMock)
    async def test_fallback_path_also_retries_transient(self, mock_sleep: AsyncMock) -> None:
        FallbackAgent._primary_failed = True
        primary = AsyncMock()
        fallback = AsyncMock()
        fallback.run.side_effect = [Exception("HTTP 429"), "fallback recovered"]

        agent = FallbackAgent(primary, fallback)
        result = await agent.run("hello")

        assert result == "fallback recovered"
        assert primary.run.call_count == 0
        assert fallback.run.call_count == 2
