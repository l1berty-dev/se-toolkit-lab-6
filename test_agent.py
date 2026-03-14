#!/usr/bin/env python3
"""Regression tests for agent.py (Task 1 and Task 2).

These tests run agent.py as a subprocess and verify:
1. The output is valid JSON
2. The 'answer' field is present
3. The 'tool_calls' field is present and is an array
4. For Task 2: tools are called correctly and source is provided

Run with: uv run pytest test_agent.py -v
"""

import json
import subprocess
import sys
from pathlib import Path


def get_agent_path() -> Path:
    """Get the path to agent.py in the project root."""
    return Path(__file__).parent / "agent.py"


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

    def test_agent_returns_answer_for_api_question(self):
        """Test that agent returns an answer for API-related questions."""
        question = "Explain what an API is."

        data, stdout, stderr = run_agent(question)

        # Check that answer is a non-empty string
        assert isinstance(data["answer"], str), (
            f"'answer' should be a string, got: {type(data['answer'])}"
        )
        assert len(data["answer"].strip()) > 0, "Answer should not be empty"


class TestAgentTask2:
    """Regression tests for Task 2: The Documentation Agent."""

    def test_merge_conflict_uses_read_file(self):
        """Test that agent uses read_file for merge conflict question."""
        question = "How do you resolve a merge conflict?"

        data, stdout, stderr = run_agent(question)

        # Check that tool_calls is not empty
        assert len(data["tool_calls"]) > 0, (
            f"Expected tool calls for wiki question, got: {data['tool_calls']}"
        )

        # Check that read_file was used
        tools_used = [tc["tool"] for tc in data["tool_calls"]]
        assert "read_file" in tools_used, (
            f"Expected 'read_file' in tool_calls, got: {tools_used}"
        )

        # Check that source contains wiki/git reference
        source = data.get("source", "")
        assert "wiki" in source.lower() or "git" in source.lower(), (
            f"Expected wiki/git reference in source, got: {source}"
        )

    def test_wiki_listing_uses_list_files(self):
        """Test that agent uses list_files for wiki listing question."""
        question = "What files are in the wiki?"

        data, stdout, stderr = run_agent(question)

        # Check that tool_calls is not empty
        assert len(data["tool_calls"]) > 0, (
            f"Expected tool calls for wiki listing question, got: {data['tool_calls']}"
        )

        # Check that list_files was used
        tools_used = [tc["tool"] for tc in data["tool_calls"]]
        assert "list_files" in tools_used, (
            f"Expected 'list_files' in tool_calls, got: {tools_used}"
        )

        # Check that answer is not empty
        assert isinstance(data["answer"], str), (
            f"'answer' should be a string, got: {type(data['answer'])}"
        )
        assert len(data["answer"].strip()) > 0, "Answer should not be empty"

    def test_tool_calls_have_required_fields(self):
        """Test that each tool call has tool, args, and result fields."""
        question = "What files are in the wiki?"

        data, stdout, stderr = run_agent(question)

        for tc in data["tool_calls"]:
            assert "tool" in tc, f"Missing 'tool' field in tool_call: {tc}"
            assert "args" in tc, f"Missing 'args' field in tool_call: {tc}"
            assert "result" in tc, f"Missing 'result' field in tool_call: {tc}"
            assert isinstance(tc["args"], dict), (
                f"'args' should be a dict, got: {type(tc['args'])}"
            )
            assert isinstance(tc["result"], str), (
                f"'result' should be a string, got: {type(tc['result'])}"
            )
