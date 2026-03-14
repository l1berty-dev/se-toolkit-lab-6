# Agent Architecture

## Overview

This agent is a Python CLI that connects to an LLM via an OpenAI-compatible API and returns structured JSON answers. It implements an **agentic loop** with three tools (`read_file`, `list_files`, `query_api`) to explore the project wiki, read source code, and query the backend API.

## LLM Provider

**Provider:** Qwen Code API (self-hosted via qwen-code-oai-proxy on a VM)

**Model:** `qwen3-coder-plus`

## Configuration

The agent reads configuration from environment variables:

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` or env |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` or env |
| `LLM_MODEL` | Model name | `.env.agent.secret` or env |
| `LMS_API_KEY` | Backend API key for query_api | `.env.docker.secret` or env |
| `AGENT_API_BASE_URL` | Base URL for query_api | Environment (default: `http://localhost:42002`) |

**Important:** The autochecker injects different values at runtime. Never hardcode these values.

## Architecture

### Components

1. **Environment Loader** - Parses `.env` files and environment variables
2. **Tools:**
   - `read_file(path)` - Read file contents from project repository
   - `list_files(path)` - List directory contents
   - `query_api(method, path, body, use_auth)` - Call backend API with optional auth
3. **LLM Client** - Sends requests to LLM API with tool definitions
4. **Agentic Loop** - Executes tool calls and feeds results back to LLM (max 20 calls)
5. **CLI Entry Point** - Parses arguments, outputs JSON to stdout

## Tool Definitions

### `read_file`
Read file contents. Security: rejects paths with `..` or outside project root.

### `list_files`
List directory contents. Security: same as read_file.

### `query_api`
Call backend API with:
- `method`: HTTP method (GET, POST, etc.)
- `path`: API endpoint
- `body`: Optional JSON body
- `use_auth`: Whether to include LMS_API_KEY header (default: true)

## Agentic Loop

```
1. Initialize messages = [system_prompt, user_question]
2. Loop (max 20 iterations):
   a. Call LLM with messages + tool definitions
   b. If tool_calls: execute tools, append results, continue
   c. If text answer: extract answer and source, return JSON
3. If max iterations: get final summary from LLM
```

## System Prompt

The system prompt guides the LLM to:
- Use `list_files`/`read_file` for wiki questions
- Use `read_file` for source code questions
- Use `query_api` for data queries
- Use `query_api` with `use_auth=false` for auth testing
- Include source file paths in answers

## Output Format

```json
{
  "answer": "There are 44 items in the database.",
  "source": "",
  "tool_calls": [
    {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}, "result": "..."}
  ]
}
```

## Testing

Run tests: `uv run pytest test_agent.py -v`

9 tests covering Task 1, 2, and 3 requirements.

## Benchmark Performance

**Score: 8/10 (80%)**

Passing: Wiki questions, framework detection, API queries, bug diagnosis.
Failing: Complex LLM judge questions (HTTP request journey, ETL idempotency).

## Lessons Learned

1. **Source extraction is critical** - Many questions require a `source` field. The `extract_source()` function uses regex patterns to find file references.

2. **Tool descriptions matter** - Clear descriptions help the LLM choose the right tool. The `use_auth` parameter enables authentication testing.

3. **Max tool calls tuning** - Started with 10, increased to 20 for complex questions.

4. **System prompt iteration** - Evolved to explicitly guide tool selection and bug diagnosis workflow.

5. **Environment variable flexibility** - Agent checks both files and environment for autochecker compatibility.

6. **LLM judge questions** - Questions requiring multi-file analysis and complex reasoning are challenging. The agent needs better synthesis capabilities.
