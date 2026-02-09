"""Log Analyzer Agent for parsing CI/CD build logs."""

import json
import logging
import re
from typing import Any

from agent_framework import Agent, AgentResponse
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import DefaultAzureCredential

from ..config import get_settings
from ..models import LogAnalysis
from ..tools.github_tools import GitHubTools
from .base import get_agent_prompt

logger = logging.getLogger(__name__)


class LogAnalyzerAgent:
    """Agent for analyzing CI/CD build logs.
    
    This agent fetches logs from GitHub Actions and extracts
    relevant error information for diagnosis.
    """

    def __init__(
        self,
        github_tools: GitHubTools,
        azure_credential: DefaultAzureCredential | None = None,
    ):
        """Initialize the Log Analyzer Agent.
        
        Args:
            github_tools: GitHub tools for fetching logs
            azure_credential: Azure credential for OpenAI
        """
        self._github_tools = github_tools
        self._credential = azure_credential or DefaultAzureCredential()
        self._settings = get_settings()
        self._agent: Agent | None = None

    async def _get_agent(self) -> Agent:
        """Get or create the agent instance."""
        if self._agent is None:
            client = AzureOpenAIResponsesClient(
                endpoint=self._settings.azure_openai_endpoint,
                deployment_name=self._settings.azure_openai_deployment_name,
                api_version=self._settings.azure_openai_api_version,
                credential=self._credential,
            )
            
            self._agent = client.create_agent(
                name="LogAnalyzer",
                instructions=get_agent_prompt("log_analyzer"),
            )
        
        return self._agent

    async def analyze(
        self,
        owner: str,
        repo: str,
        run_id: int,
    ) -> list[LogAnalysis]:
        """Analyze logs from a failed workflow run.
        
        Args:
            owner: Repository owner
            repo: Repository name
            run_id: Workflow run ID
            
        Returns:
            List of log analysis results for each failed job
        """
        logger.info(f"Analyzing logs for {owner}/{repo} run {run_id}")
        
        # Fetch logs for failed jobs
        try:
            logs = await self._github_tools.get_failed_jobs_logs(owner, repo, run_id)
        except Exception as e:
            logger.error(f"Failed to fetch logs: {e}")
            raise
        
        if not logs:
            logger.warning(f"No failed jobs found for run {run_id}")
            return []
        
        analyses: list[LogAnalysis] = []
        
        for job_name, raw_logs in logs.items():
            try:
                analysis = await self._analyze_job_logs(job_name, raw_logs)
                analyses.append(analysis)
            except Exception as e:
                logger.error(f"Failed to analyze logs for job {job_name}: {e}")
                # Create a basic analysis with the error
                analyses.append(LogAnalysis(
                    job_id=0,
                    job_name=job_name,
                    raw_logs=raw_logs[:10000],  # Truncate very long logs
                    error_lines=["Failed to analyze logs"],
                    summary=f"Analysis failed: {e}",
                ))
        
        return analyses

    async def _analyze_job_logs(
        self,
        job_name: str,
        raw_logs: str,
    ) -> LogAnalysis:
        """Analyze logs from a single job.
        
        Args:
            job_name: Name of the job
            raw_logs: Raw log content
            
        Returns:
            Log analysis result
        """
        # Pre-process logs to extract key information
        error_lines = self._extract_error_lines(raw_logs)
        warning_lines = self._extract_warning_lines(raw_logs)
        key_events = self._extract_key_events(raw_logs)
        
        # Use the agent to generate a summary
        agent = await self._get_agent()
        
        # Truncate logs for the prompt
        truncated_logs = raw_logs[:15000] if len(raw_logs) > 15000 else raw_logs
        
        prompt = f"""Analyze the following CI/CD build logs and provide a summary.

Job Name: {job_name}

Extracted Error Lines:
{chr(10).join(error_lines[:20])}

Extracted Warnings:
{chr(10).join(warning_lines[:10])}

Key Events:
{chr(10).join(key_events[:10])}

Raw Logs (truncated):
```
{truncated_logs}
```

Provide a concise summary of:
1. What failed and why
2. The specific error messages
3. Any relevant context from the logs
"""
        
        try:
            response = await agent.run(prompt)
            summary = str(response) if response else "No summary generated"
        except Exception as e:
            logger.error(f"Agent failed to generate summary: {e}")
            summary = f"Summary generation failed. Key errors: {'; '.join(error_lines[:5])}"
        
        return LogAnalysis(
            job_id=0,  # Would need to be passed in for actual job ID
            job_name=job_name,
            raw_logs=raw_logs[:50000],  # Store truncated logs
            error_lines=error_lines,
            warning_lines=warning_lines,
            key_events=key_events,
            summary=summary,
        )

    def _extract_error_lines(self, logs: str) -> list[str]:
        """Extract lines containing errors from logs.
        
        Args:
            logs: Raw log content
            
        Returns:
            List of error lines
        """
        error_patterns = [
            r"(?i)error[:\s]",
            r"(?i)failed[:\s]",
            r"(?i)exception[:\s]",
            r"(?i)fatal[:\s]",
            r"(?i)cannot find",
            r"(?i)not found",
            r"(?i)undefined",
            r"(?i)npm ERR!",
            r"(?i)pip.*error",
            r"(?i)ModuleNotFoundError",
            r"(?i)ImportError",
            r"(?i)SyntaxError",
            r"(?i)TypeError",
            r"(?i)AssertionError",
            r"FAIL\s",
            r"✕|✖|❌",
        ]
        
        combined_pattern = "|".join(error_patterns)
        error_lines: list[str] = []
        
        for line in logs.split("\n"):
            line = line.strip()
            if line and re.search(combined_pattern, line):
                # Clean up timestamps and ANSI codes
                clean_line = self._clean_log_line(line)
                if clean_line and len(clean_line) < 500:  # Skip very long lines
                    error_lines.append(clean_line)
        
        return error_lines[:100]  # Limit to 100 error lines

    def _extract_warning_lines(self, logs: str) -> list[str]:
        """Extract lines containing warnings from logs.
        
        Args:
            logs: Raw log content
            
        Returns:
            List of warning lines
        """
        warning_patterns = [
            r"(?i)warning[:\s]",
            r"(?i)warn[:\s]",
            r"(?i)deprecated",
            r"(?i)⚠",
        ]
        
        combined_pattern = "|".join(warning_patterns)
        warning_lines: list[str] = []
        
        for line in logs.split("\n"):
            line = line.strip()
            if line and re.search(combined_pattern, line):
                clean_line = self._clean_log_line(line)
                if clean_line and len(clean_line) < 500:
                    warning_lines.append(clean_line)
        
        return warning_lines[:50]  # Limit to 50 warning lines

    def _extract_key_events(self, logs: str) -> list[str]:
        """Extract key events from logs (step starts, completions, etc).
        
        Args:
            logs: Raw log content
            
        Returns:
            List of key events
        """
        event_patterns = [
            r"##\[group\](.+)",
            r"Run (.+)",
            r"(?i)starting (.+)",
            r"(?i)installing (.+)",
            r"(?i)building (.+)",
            r"(?i)testing (.+)",
            r"(?i)completed (.+)",
        ]
        
        events: list[str] = []
        
        for pattern in event_patterns:
            matches = re.findall(pattern, logs)
            for match in matches[:10]:  # Limit matches per pattern
                if isinstance(match, str) and match.strip():
                    events.append(match.strip()[:200])
        
        return events[:30]  # Limit to 30 events

    def _clean_log_line(self, line: str) -> str:
        """Clean a log line by removing timestamps and ANSI codes.
        
        Args:
            line: Raw log line
            
        Returns:
            Cleaned log line
        """
        # Remove ANSI escape codes
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        line = ansi_escape.sub('', line)
        
        # Remove common timestamp patterns
        timestamp_patterns = [
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s*",
            r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s*",
            r"^\[\d{2}:\d{2}:\d{2}\]\s*",
        ]
        
        for pattern in timestamp_patterns:
            line = re.sub(pattern, "", line)
        
        return line.strip()
