"""Regression tests for agent.py CLI.

These tests run agent.py as a subprocess and verify:
1. The output is valid JSON
2. Required fields (answer, tool_calls) are present
3. The answer is non-empty

Run with: uv run pytest backend/tests/unit/test_agent.py -v

Note: These tests require a valid LLM API configuration in .env.agent.secret.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


# Path to agent.py in project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
AGENT_PATH = PROJECT_ROOT / "agent.py"


class TestAgentOutput:
    """Test that agent.py produces valid JSON output with required fields."""

    @pytest.mark.asyncio
    async def test_agent_returns_valid_json(self):
        """Test that agent.py outputs valid JSON."""
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), "What is 2 + 2?"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Check exit code
        assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"

        # Check stdout is not empty
        assert result.stdout.strip(), "Agent produced no output"

        # Check output is valid JSON
        try:
            data = json.loads(result.stdout.strip())
        except json.JSONDecodeError as e:
            pytest.fail(f"Agent output is not valid JSON: {result.stdout[:200]}. Error: {e}")

    @pytest.mark.asyncio
    async def test_agent_has_answer_field(self):
        """Test that agent output contains 'answer' field."""
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), "What is the capital of France?"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"

        data = json.loads(result.stdout.strip())

        assert "answer" in data, "Missing 'answer' field in output"
        assert isinstance(data["answer"], str), "'answer' should be a string"
        assert len(data["answer"].strip()) > 0, "'answer' should not be empty"

    @pytest.mark.asyncio
    async def test_agent_has_tool_calls_field(self):
        """Test that agent output contains 'tool_calls' field as an array."""
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), "Explain what Python is."],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"

        data = json.loads(result.stdout.strip())

        assert "tool_calls" in data, "Missing 'tool_calls' field in output"
        assert isinstance(data["tool_calls"], list), "'tool_calls' should be an array"
