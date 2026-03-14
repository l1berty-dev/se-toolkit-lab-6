"""Regression tests for agent.py (Task 1).

These tests run agent.py as a subprocess and verify:
1. The output is valid JSON
2. The 'answer' field is present
3. The 'tool_calls' field is present and is an array

Run with: uv run pytest backend/tests/unit/test_agent_task1.py -v
"""

import json
import subprocess
import sys
from pathlib import Path


def get_agent_path() -> Path:
    """Get the path to agent.py in the project root."""
    # backend/tests/unit -> project root
    return Path(__file__).parent.parent.parent.parent / "agent.py"


def run_agent(question: str) -> tuple[dict, str, str]:
    """Run agent.py with a question and return the parsed output.

    Args:
        question: The question to ask the agent

    Returns:
        Tuple of (parsed_json_dict, stdout, stderr)

    Raises:
        subprocess.CalledProcessError: If agent exits with non-zero code
        json.JSONDecodeError: If output is not valid JSON
    """
    agent_path = get_agent_path()

    result = subprocess.run(
        [sys.executable, str(agent_path), question],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check for non-zero exit code
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            [sys.executable, str(agent_path), question],
            result.stdout,
            result.stderr,
        )

    # Parse JSON output
    data = json.loads(result.stdout)

    return data, result.stdout, result.stderr


class TestAgentTask1:
    """Regression tests for Task 1: Call an LLM from Code."""

    def test_agent_returns_valid_json(self):
        """Test that agent.py returns valid JSON with required fields."""
        question = "What is 2+2?"

        data, stdout, stderr = run_agent(question)

        # Check that 'answer' field exists
        assert "answer" in data, f"Missing 'answer' field in output: {stdout}"

        # Check that 'tool_calls' field exists
        assert "tool_calls" in data, f"Missing 'tool_calls' field in output: {stdout}"

        # Check that 'tool_calls' is an array
        assert isinstance(data["tool_calls"], list), (
            f"'tool_calls' should be an array, got: {type(data['tool_calls'])}"
        )

    def test_agent_answer_is_not_empty(self):
        """Test that the agent returns a non-empty answer."""
        question = "What does REST stand for?"

        data, stdout, stderr = run_agent(question)

        # Check that answer is a non-empty string
        assert isinstance(data["answer"], str), (
            f"'answer' should be a string, got: {type(data['answer'])}"
        )
        assert len(data["answer"].strip()) > 0, "Answer should not be empty"

    def test_agent_tool_calls_is_empty_array(self):
        """Test that tool_calls is an empty array for Task 1 (no tools yet)."""
        question = "Explain what an API is."

        data, stdout, stderr = run_agent(question)

        # For Task 1, tool_calls should always be empty (no tools implemented yet)
        assert data["tool_calls"] == [], (
            f"tool_calls should be empty for Task 1, got: {data['tool_calls']}"
        )
