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
MAX_TOOL_CALLS = 20

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
    """Load LLM configuration from .env.agent.secret or environment.

    Returns:
        Tuple of (api_key, api_base, model)
    """
    env_path = PROJECT_ROOT / ".env.agent.secret"
    env_vars = load_env(env_path)

    # Also check environment variables (for autochecker)
    api_key = os.environ.get("LLM_API_KEY") or env_vars.get("LLM_API_KEY", "")
    api_base = os.environ.get("LLM_API_BASE") or env_vars.get("LLM_API_BASE", "")
    model = os.environ.get("LLM_MODEL") or env_vars.get("LLM_MODEL", "")

    if not api_key:
        print("Error: LLM_API_KEY not found", file=sys.stderr)
        sys.exit(1)
    if not api_base:
        print("Error: LLM_API_BASE not found", file=sys.stderr)
        sys.exit(1)
    if not model:
        print("Error: LLM_MODEL not found", file=sys.stderr)
        sys.exit(1)

    return api_key, api_base, model


def get_lms_api_key() -> str:
    """Get the LMS API key for query_api authentication."""
    env_path = PROJECT_ROOT / ".env.docker.secret"
    env_vars = load_env(env_path)

    # Check environment first (for autochecker), then file
    api_key = os.environ.get("LMS_API_KEY") or env_vars.get("LMS_API_KEY", "")

    if not api_key:
        print("Warning: LMS_API_KEY not found - API calls may fail", file=sys.stderr)

    return api_key


def get_agent_api_base_url() -> str:
    """Get the base URL for the agent API."""
    # Check environment first (for autochecker), then default
    return os.environ.get("AGENT_API_BASE_URL", "http://localhost:42002")


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


def tool_query_api(method: str, path: str, body: str | None = None, use_auth: bool = True) -> str:
    """Call the backend API.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., '/items/')
        body: Optional JSON request body for POST/PUT requests
        use_auth: Whether to include authentication header (default: True)

    Returns:
        JSON string with status_code and body, or error message
    """
    api_base = get_agent_api_base_url()
    api_key = get_lms_api_key()

    url = f"{api_base}{path}"

    headers = {
        "Content-Type": "application/json",
    }
    
    if use_auth and api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"[query_api] {method} {url} (auth: {'yes' if use_auth else 'no'})", file=sys.stderr)

    try:
        with httpx.Client(timeout=30) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                data = json.loads(body) if body else {}
                response = client.post(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                data = json.loads(body) if body else {}
                response = client.put(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return f"Error: Unsupported method '{method}'"

            result = {
                "status_code": response.status_code,
                "body": response.text,
            }
            return json.dumps(result)

    except httpx.ConnectError as e:
        return f"Error: Cannot connect to API at {url} - {e}"
    except httpx.TimeoutException as e:
        return f"Error: API request timed out - {e}"
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON in request body - {e}"
    except Exception as e:
        return f"Error: API request failed - {e}"


# Tool definitions for the LLM
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from the project repository. Use this to read documentation files in the wiki/ directory or source code files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md' or 'backend/app/main.py')",
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
                        "description": "Relative directory path from project root (e.g., 'wiki' or 'backend/app/routers')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Call the backend API to query data or check system behavior. Use this for questions about items count, analytics, status codes, or any runtime data. To test authentication errors, set use_auth to false.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE)",
                    },
                    "path": {
                        "type": "string",
                        "description": "API endpoint path (e.g., '/items/', '/analytics/scores', '/analytics/completion-rate')",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional JSON request body for POST/PUT requests",
                    },
                    "use_auth": {
                        "type": "boolean",
                        "description": "Whether to include authentication header (default: true). Set to false to test unauthenticated access.",
                    },
                },
                "required": ["method", "path"],
            },
        },
    },
]

# Tool name to function mapping
TOOL_FUNCTIONS = {
    "read_file": tool_read_file,
    "list_files": tool_list_files,
    "query_api": tool_query_api,
}

# System prompt for the agent
SYSTEM_PROMPT = """You are a helpful assistant with access to a project wiki, source code, and a backend API.

You have three tools:
1. list_files(path) - List files in a directory
2. read_file(path) - Read the contents of a file
3. query_api(method, path, body, use_auth) - Call the backend API

When answering questions:
- For wiki/documentation questions: use list_files and read_file on wiki/ files
- For source code questions: use read_file to read .py files in backend/app/
- For data queries (items count, scores, analytics): use query_api with use_auth=true
- For status code questions about unauthenticated access: use query_api with use_auth=false
- For system architecture questions: read docker-compose.yml and source files
- For bug diagnosis: 
  1. Use query_api to reproduce the error and see the error message
  2. Read the relevant source file to find the bug
  3. Identify the specific line and explain the bug (e.g., NoneType, division by zero, TypeError)

IMPORTANT: Always include the source file path in your answer using the exact format:
- For wiki files: wiki/filename.md (e.g., wiki/github.md, wiki/git-workflow.md)
- For source files: backend/app/filename.py (e.g., backend/app/analytics.py)
- For config files: docker-compose.yml, etc.

Be efficient with tool calls. After gathering information, provide a complete, direct answer.
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
            answer = assistant_message.get("content") or ""

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
            "content": "Based on the information gathered, please provide a final answer with a source reference if applicable.",
        }
    )

    response = call_llm(messages, api_key, api_base, model)
    answer = response["choices"][0]["message"].get("content") or ""
    source = extract_source(answer)

    return answer, source, tool_calls_log


def extract_source(answer: str) -> str:
    """Extract or generate a source reference from the answer.

    Looks for patterns like 'wiki/filename.md' or 'wiki/filename.md#section'
    Also looks for backend/app/*.py files and other source references.
    """
    import re

    # Look for wiki file references (with optional section anchor)
    pattern = r"(wiki/[\w\-]+\.md(?:#[\w\-]+)?)"
    match = re.search(pattern, answer, re.IGNORECASE)

    if match:
        return match.group(1).lower()

    # Look for backend source file references
    pattern2 = r"(backend/app/[\w\-]+\.py)"
    match2 = re.search(pattern2, answer, re.IGNORECASE)

    if match2:
        return match2.group(1).lower()

    # Look for docker-compose.yml references
    pattern3 = r"(docker-compose\.yml)"
    match3 = re.search(pattern3, answer, re.IGNORECASE)

    if match3:
        return match3.group(1).lower()

    # Look for plain .md file references in wiki context (e.g., "github.md" when talking about wiki)
    # This handles cases where LLM says "in the github.md file"
    wiki_files = [
        "git-workflow.md", "github.md", "git.md", "git-vscode.md", "gitlens.md",
        "ssh.md", "vm.md", "docker.md", "docker-compose.md", "linux.md",
        "api.md", "web-api.md", "rest-api.md", "http.md", "http-auth.md",
        "python.md", "fastapi.md", "sql.md", "database.md", "postgresql.md",
        "coding-agents.md", "llm.md", "qwen.md", "security.md", "file-system.md",
        "cli.md", "shell.md", "bash.md", "terminal.md", "vs-code.md",
        "environments.md", "docker-postgres.md", "caddy.md", "frontend.md",
        "backend.md", "architecture.md", "architectural-views.md",
        "communication-protocol.md", "computer-networks.md",
        "database-modeling.md", "direnv.md", "dotenv-docker-secret.md",
        "dotenv-tests-e2e-secret.md", "dotenv-tests-unit-secret.md",
        "file-formats.md", "frontend-dotenv-secret.md", "github.md",
        "lab.md", "linux-distros.md", "nix.md", "nix-devshell.md", "nix-flake.md",
        "nodejs.md", "operating-system.md", "package-manager.md", "pgadmin.md",
        "programming-language.md", "pyproject-toml.md", "quality-assurance.md",
        "requirements.md", "software-types.md", "swagger.md",
        "useful-programs.md", "visualize-architecture.md", "vm-autochecker.md",
        "vm-hardening.md", "vm-info.md", "vscode-python.md", "web-infrastructure.md",
        "autochecker.md", "browser-developer-tools.md", "coding-agents.md",
    ]
    
    for wiki_file in wiki_files:
        # Look for mentions of the file without the wiki/ prefix
        if re.search(rf"\b{re.escape(wiki_file)}\b", answer, re.IGNORECASE):
            return f"wiki/{wiki_file}".lower()

    # Look for backend/app router and module files mentioned by name
    backend_files = [
        "analytics.py", "items.py", "interactions.py", "learners.py", "pipeline.py",
        "main.py", "auth.py", "database.py", "etl.py", "settings.py", "run.py",
    ]
    
    for backend_file in backend_files:
        if re.search(rf"\b{re.escape(backend_file)}\b", answer, re.IGNORECASE):
            return f"backend/app/{backend_file}".lower()
        # Also check for routers/ subdirectory
        if re.search(rf"\brouters/{re.escape(backend_file)}\b", answer, re.IGNORECASE):
            return f"backend/app/routers/{backend_file}".lower()

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
    print(f"API Base URL: {get_agent_api_base_url()}", file=sys.stderr)

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
