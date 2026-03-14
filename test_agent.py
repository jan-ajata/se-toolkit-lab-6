"""Regression tests for agent.py CLI.

These tests run agent.py as a subprocess and verify:
1. The output is valid JSON
2. Required fields (answer, source, tool_calls) are present
3. The answer is non-empty
4. Tool calls are populated when tools are used
5. Source field correctly identifies wiki sections

Run with: uv run pytest test_agent.py -v

Note: These tests require a valid LLM API configuration in .env.agent.secret.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


# Path to agent.py in project root (same directory as this test file)
PROJECT_ROOT = Path(__file__).parent
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


class TestDocumentationAgent:
    """Test that agent.py correctly uses tools to answer wiki questions."""

    @pytest.mark.asyncio
    async def test_merge_conflict_uses_read_file(self):
        """Test that agent uses read_file to answer merge conflict question.
        
        The agent should discover wiki files and read git-workflow.md or git-vscode.md
        to find information about resolving merge conflicts.
        """
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), "How do you resolve a merge conflict?"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"

        data = json.loads(result.stdout.strip())

        # Check required fields
        assert "answer" in data, "Missing 'answer' field"
        assert "source" in data, "Missing 'source' field"
        assert "tool_calls" in data, "Missing 'tool_calls' field"

        # Check that tool_calls is populated
        assert len(data["tool_calls"]) > 0, "Expected tool calls but got none"

        # Check that read_file was used
        tools_used = [call["tool"] for call in data["tool_calls"]]
        assert "read_file" in tools_used, f"Expected read_file in tool calls, got: {tools_used}"

        # Check that source references a wiki file
        # Source may be in format "wiki/file.md#section" or just "file.md#section"
        source = data["source"].lower()
        has_wiki_path = "wiki/" in source or "git" in source
        assert has_wiki_path, f"Source should reference a wiki file, got: {data['source']}"

    @pytest.mark.asyncio
    async def test_wiki_files_uses_list_files(self):
        """Test that agent uses list_files to discover wiki files.
        
        When asked about files in the wiki, the agent should use list_files
        to discover what files exist.
        """
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), "What files are in the wiki?"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"

        data = json.loads(result.stdout.strip())

        # Check required fields
        assert "answer" in data, "Missing 'answer' field"
        assert "tool_calls" in data, "Missing 'tool_calls' field"

        # Check that tool_calls is populated
        assert len(data["tool_calls"]) > 0, "Expected tool calls but got none"

        # Check that list_files was used
        tools_used = [call["tool"] for call in data["tool_calls"]]
        assert "list_files" in tools_used, f"Expected list_files in tool calls, got: {tools_used}"

        # Check that the list_files result contains wiki files
        for call in data["tool_calls"]:
            if call["tool"] == "list_files" and call["args"].get("path") == "wiki":
                assert "git" in call["result"].lower(), "list_files result should contain git files"
                break
        else:
            pytest.fail("list_files with path 'wiki' was not called")


class TestSystemAgent:
    """Test that agent.py correctly uses query_api for system questions."""

    @pytest.mark.asyncio
    async def test_framework_question_uses_read_file(self):
        """Test that agent uses read_file to answer framework question.
        
        When asked about the Python web framework, the agent should read
        the backend source code to find FastAPI.
        """
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), "What Python web framework does the backend use?"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"

        data = json.loads(result.stdout.strip())

        # Check required fields
        assert "answer" in data, "Missing 'answer' field"
        assert "tool_calls" in data, "Missing 'tool_calls' field"

        # Check that tool_calls is populated
        assert len(data["tool_calls"]) > 0, "Expected tool calls but got none"

        # Check that read_file was used
        tools_used = [call["tool"] for call in data["tool_calls"]]
        assert "read_file" in tools_used, f"Expected read_file in tool calls, got: {tools_used}"

        # Check that the answer mentions FastAPI
        assert "fastapi" in data["answer"].lower(), f"Answer should mention FastAPI, got: {data['answer']}"

    @pytest.mark.asyncio
    async def test_database_count_uses_query_api(self):
        """Test that agent uses query_api to answer database count question.
        
        When asked about the number of items in the database, the agent
        should query the /items/ endpoint.
        """
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), "How many items are currently stored in the database?"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"

        data = json.loads(result.stdout.strip())

        # Check required fields
        assert "answer" in data, "Missing 'answer' field"
        assert "tool_calls" in data, "Missing 'tool_calls' field"

        # Check that tool_calls is populated
        assert len(data["tool_calls"]) > 0, "Expected tool calls but got none"

        # Check that query_api was used
        tools_used = [call["tool"] for call in data["tool_calls"]]
        assert "query_api" in tools_used, f"Expected query_api in tool calls, got: {tools_used}"

        # Check that the answer contains a number
        import re
        numbers = re.findall(r'\d+', data["answer"])
        assert len(numbers) > 0, f"Answer should contain a number, got: {data['answer']}"
