# Task 3 Plan: The System Agent

## Overview

This task extends the Task 2 agent with a `query_api` tool that can call the deployed backend API. The agent will answer both static system questions (framework, ports) and data-dependent queries (item count, scores).

## Tool Definition: `query_api`

**Purpose:** Call the deployed backend API with authentication.

**Schema:**
```json
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
          "description": "HTTP method (GET, POST, PUT, DELETE)"
        },
        "path": {
          "type": "string",
          "description": "API endpoint path (e.g., '/items/', '/analytics/scores', '/analytics/completion-rate')"
        },
        "body": {
          "type": "string",
          "description": "Optional JSON request body for POST/PUT requests"
        },
        "use_auth": {
          "type": "boolean",
          "description": "Whether to include authentication header (default: true). Set to false to test unauthenticated access."
        }
      },
      "required": ["method", "path"]
    }
  }
}
```

**Implementation:**
- Use `httpx` to make HTTP requests
- Read `LMS_API_KEY` from `.env.docker.secret` for authentication
- Read `AGENT_API_BASE_URL` from environment (default: `http://localhost:42002`)
- Send `Authorization: Bearer {LMS_API_KEY}` header when `use_auth=true`
- Return JSON string with `status_code` and `body`

## Environment Variables

The agent must read configuration from environment variables:

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` or env |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` or env |
| `LLM_MODEL` | Model name | `.env.agent.secret` or env |
| `LMS_API_KEY` | Backend API key for query_api auth | `.env.docker.secret` or env |
| `AGENT_API_BASE_URL` | Base URL for query_api (optional) | Environment, defaults to `http://localhost:42002` |

**Important:** The autochecker injects different values at runtime. Never hardcode these values.

## System Prompt Update

The system prompt guides the LLM to choose the right tool:

- For wiki/documentation questions: use `list_files` and `read_file` on wiki/ files
- For source code questions: use `read_file` to read .py files in backend/app/
- For data queries: use `query_api` with `use_auth=true`
- For status code questions without auth: use `query_api` with `use_auth=false`
- For bug diagnosis: use `query_api` to reproduce error, then `read_file` to find bug

Always include source file paths in answers (e.g., `wiki/github.md`, `backend/app/analytics.py`).

## Agentic Loop

Same as Task 2, but with max 20 tool calls for complex questions.

## Benchmark Results

**Score: 8/10 (80%)**

### Passing (8):
1. Wiki branch protection
2. Wiki SSH connection  
3. Backend framework (FastAPI)
4. API router listing
5. Database items count
6. Unauthenticated status code (401)
7. Completion-rate bug (ZeroDivisionError)
8. Top-learners bug (TypeError/NoneType)

### Failing (2 - LLM judge questions):
9. HTTP request journey (complex multi-file reasoning)
10. ETL pipeline idempotency (complex reasoning)

## Files Modified

1. `agent.py` - Added `query_api` tool with `use_auth` parameter
2. `AGENT.md` - Updated documentation (200+ words)
3. `test_agent.py` - Added 3 regression tests for Task 3
