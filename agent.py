#!/usr/bin/env python3
"""Agent CLI with tools and agentic loop.

Usage:
    uv run agent.py "Your question here"

Output:
    A single JSON line to stdout:
    {"answer": "...", "source": "...", "tool_calls": [...]}

All debug output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

# Maximum number of tool calls per question
MAX_TOOL_CALLS = 10

# Project root directory
PROJECT_ROOT = Path(__file__).parent


def load_env(env_path: Path) -> dict[str, str]:
    """Load environment variables from a simple KEY=value file."""
    env_vars = {}
    if not env_path.exists():
        return env_vars

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            env_vars[key] = value

    return env_vars


def get_llm_config() -> tuple[str, str, str]:
    """Load LLM configuration from .env.agent.secret.

    Returns:
        Tuple of (api_key, api_base, model)
    """
    env_path = PROJECT_ROOT / ".env.agent.secret"

    env_vars = load_env(env_path)

    api_key = env_vars.get("LLM_API_KEY", "")
    api_base = env_vars.get("LLM_API_BASE", "")
    model = env_vars.get("LLM_MODEL", "")

    if not api_key:
        print("Error: LLM_API_KEY not found in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not api_base:
        print("Error: LLM_API_BASE not found in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not model:
        print("Error: LLM_MODEL not found in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    return api_key, api_base, model


def is_safe_path(requested_path: str) -> bool:
    """Check if the requested path is safe (within project root).

    Security: Rejects paths containing '..' or that resolve outside project root.
    """
    # Reject paths with directory traversal
    if ".." in requested_path:
        return False

    # Resolve the path and check it's within project root
    try:
        full_path = (PROJECT_ROOT / requested_path).resolve()
        return full_path.is_relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return False


def tool_read_file(path: str) -> str:
    """Read a file from the project repository.

    Args:
        path: Relative path from project root

    Returns:
        File contents as string, or error message
    """
    if not is_safe_path(path):
        return f"Error: Access denied - path '{path}' is not allowed"

    file_path = PROJECT_ROOT / path

    if not file_path.exists():
        return f"Error: File not found - '{path}'"

    if not file_path.is_file():
        return f"Error: Not a file - '{path}'"

    try:
        return file_path.read_text()
    except Exception as e:
        return f"Error reading file: {e}"


def tool_list_files(path: str) -> str:
    """List files and directories at a given path.

    Args:
        path: Relative directory path from project root

    Returns:
        Newline-separated listing of entries, or error message
    """
    if not is_safe_path(path):
        return f"Error: Access denied - path '{path}' is not allowed"

    dir_path = PROJECT_ROOT / path

    if not dir_path.exists():
        return f"Error: Directory not found - '{path}'"

    if not dir_path.is_dir():
        return f"Error: Not a directory - '{path}'"

    try:
        entries = sorted([entry.name for entry in dir_path.iterdir()])
        return "\n".join(entries)
    except Exception as e:
        return f"Error listing directory: {e}"


# Tool definitions for the LLM
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from the project repository. Use this to read documentation files in the wiki/ directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path. Use this to discover what files exist in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki')",
                    }
                },
                "required": ["path"],
            },
        },
    },
]

# Tool name to function mapping
TOOL_FUNCTIONS = {
    "read_file": tool_read_file,
    "list_files": tool_list_files,
}

# System prompt for the agent
SYSTEM_PROMPT = """You are a helpful assistant with access to a project wiki.

You have two tools:
- list_files(path): List files in a directory
- read_file(path): Read the contents of a file

When answering questions about the project:
1. First use list_files("wiki") to discover available documentation
2. Use read_file() to read relevant files and find accurate information
3. Include the source file path and section in your final answer
4. Format source as: wiki/filename.md#section-anchor (use lowercase, replace spaces with hyphens)

Think step-by-step and use your tools to find accurate answers from the wiki.
Always provide a source reference for your answer.
"""


def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Execute a tool and return the result.

    Args:
        tool_name: Name of the tool to execute
        args: Arguments for the tool

    Returns:
        Tool result as a string
    """
    if tool_name not in TOOL_FUNCTIONS:
        return f"Error: Unknown tool '{tool_name}'"

    func = TOOL_FUNCTIONS[tool_name]
    try:
        return func(**args)
    except TypeError as e:
        return f"Error: Invalid arguments for {tool_name}: {e}"
    except Exception as e:
        return f"Error executing {tool_name}: {e}"


def call_llm(
    messages: list[dict[str, Any]],
    api_key: str,
    api_base: str,
    model: str,
    timeout: int = 60,
) -> dict[str, Any]:
    """Call the LLM API and return the response.

    Args:
        messages: List of message dicts for the conversation
        api_key: API key for authentication
        api_base: Base URL of the API
        model: Model name to use
        timeout: Request timeout in seconds

    Returns:
        The LLM response as a dict
    """
    url = f"{api_base}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOL_DEFINITIONS,
        "tool_choice": "auto",
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def run_agentic_loop(
    question: str, api_key: str, api_base: str, model: str
) -> tuple[str, str, list[dict[str, Any]]]:
    """Run the agentic loop to answer a question.

    Args:
        question: The user's question
        api_key: API key for authentication
        api_base: Base URL of the API
        model: Model name to use

    Returns:
        Tuple of (answer, source, tool_calls)
    """
    # Initialize conversation
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_calls_log = []
    tool_call_count = 0

    while tool_call_count < MAX_TOOL_CALLS:
        print(f"\n[Loop iteration {tool_call_count + 1}]", file=sys.stderr)

        # Call LLM
        response = call_llm(messages, api_key, api_base, model)

        # Get the assistant message
        assistant_message = response["choices"][0]["message"]

        # Check for tool calls
        tool_calls = assistant_message.get("tool_calls", [])

        if not tool_calls:
            # No tool calls - LLM provided final answer
            print("[LLM provided final answer]", file=sys.stderr)
            answer = assistant_message.get("content", "")

            # Extract source from answer (look for file references)
            source = extract_source(answer)

            return answer, source, tool_calls_log

        # Execute tool calls
        messages.append(assistant_message)

        for tool_call in tool_calls:
            tool_call_id = tool_call["id"]
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])

            print(f"[Executing tool: {tool_name}({tool_args})]", file=sys.stderr)

            # Execute the tool
            result = execute_tool(tool_name, tool_args)

            # Log the tool call
            tool_calls_log.append(
                {
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result,
                }
            )

            # Add tool result to messages
            messages.append(
                {
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tool_call_id,
                }
            )

            tool_call_count += 1

            if tool_call_count >= MAX_TOOL_CALLS:
                print(
                    f"[Max tool calls ({MAX_TOOL_CALLS}) reached]", file=sys.stderr
                )
                break

    # Max iterations reached - use whatever answer we have
    # Make one final call to get a summary answer
    print("[Max iterations reached, getting final answer]", file=sys.stderr)

    messages.append(
        {
            "role": "system",
            "content": "Based on the information gathered, please provide a final answer with a source reference.",
        }
    )

    response = call_llm(messages, api_key, api_base, model)
    answer = response["choices"][0]["message"].get("content", "")
    source = extract_source(answer)

    return answer, source, tool_calls_log


def extract_source(answer: str) -> str:
    """Extract or generate a source reference from the answer.

    Looks for patterns like 'wiki/filename.md' or 'wiki/filename.md#section'
    """
    import re

    # Look for wiki file references
    pattern = r"(wiki/[\w\-]+\.md(?:#[\w\-]+)?)"
    match = re.search(pattern, answer, re.IGNORECASE)

    if match:
        return match.group(1).lower()

    return ""


def main() -> None:
    """Main entry point."""
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"Your question here\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # Load configuration
    api_key, api_base, model = get_llm_config()

    print(f"Question: {question}", file=sys.stderr)
    print(f"Using model: {model}", file=sys.stderr)

    # Run the agentic loop
    answer, source, tool_calls = run_agentic_loop(question, api_key, api_base, model)

    print(f"\nAnswer received", file=sys.stderr)
    if source:
        print(f"Source: {source}", file=sys.stderr)

    # Output JSON result
    result = {
        "answer": answer,
        "source": source,
        "tool_calls": tool_calls,
    }

    # Output only JSON to stdout (single line)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
