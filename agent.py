#!/usr/bin/env python3
"""Agent CLI - calls an LLM and returns a JSON answer.

Usage:
    uv run agent.py "Your question here"

Output:
    A single JSON line to stdout:
    {"answer": "...", "tool_calls": []}

All debug output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path

import httpx


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
    project_root = Path(__file__).parent
    env_path = project_root / ".env.agent.secret"

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


def call_lllm(question: str, api_key: str, api_base: str, model: str, timeout: int = 60) -> str:
    """Call the LLM API and return the answer.

    Args:
        question: The user's question
        api_key: API key for authentication
        api_base: Base URL of the API (should include /v1)
        model: Model name to use
        timeout: Request timeout in seconds

    Returns:
        The LLM's answer as a string
    """
    url = f"{api_base}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant. Answer questions concisely and accurately.",
            },
            {"role": "user", "content": question},
        ],
    }

    print(f"Calling LLM API at {url}...", file=sys.stderr)

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()

    # Extract the answer from the response
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        print(f"Error: Unexpected API response format: {e}", file=sys.stderr)
        print(f"Response: {data}", file=sys.stderr)
        sys.exit(1)

    return answer


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

    # Call the LLM
    answer = call_lllm(question, api_key, api_base, model)

    print(f"Answer received", file=sys.stderr)

    # Output JSON result
    result = {
        "answer": answer,
        "tool_calls": [],
    }

    # Output only JSON to stdout (single line)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
