# Agent Architecture

## Overview

This agent is a Python CLI that connects to an LLM via an OpenAI-compatible API and returns structured JSON answers. It implements an **agentic loop** with three tools (`read_file`, `list_files`, `query_api`) to explore the project wiki, read source code, and query the backend API.

## LLM Provider

**Provider:** Qwen Code API (self-hosted via qwen-code-oai-proxy on a VM)

**Model:** `qwen3-coder-plus`

**Why Qwen Code:**
- 1000 free requests per day
- Available in Russia
- No credit card required
- OpenAI-compatible API with tool calling support

## Configuration

The agent reads configuration from environment variables (with fallback to files):

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` or env |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` or env |
| `LLM_MODEL` | Model name | `.env.agent.secret` or env |
| `LMS_API_KEY` | Backend API key for query_api | `.env.docker.secret` or env |
| `AGENT_API_BASE_URL` | Base URL for query_api | Environment (default: `http://localhost:42002`) |

**Important:** The autochecker injects different values at runtime. Never hardcode these values.

## Architecture

### Data Flow

```
┌─────────────┐     ┌──────────┐     ┌─────────────┐
│  Command    │────▶│ agent.py │────▶│  LLM API    │
│  Question   │     │  CLI     │     │  (Qwen)     │
└─────────────┘     └──────────┘     └─────────────┘
                         │                  │
                         │◀──── Tool ───────│
                         │    Calls         │
                         ▼
                  ┌─────────────┐
                  │  Tools      │
                  │  - read_file│
                  │  - list_files│
                  │  - query_api│
                  └─────────────┘
                         │
                         ▼
                  ┌─────────────┐
                  │  JSON       │
                  │  Output     │
                  └─────────────┘
```

### Components

1. **Environment Loader** (`load_env`)
   - Parses `.env.agent.secret` and `.env.docker.secret` files
   - Simple KEY=value format (no external dependencies)
   - Also checks environment variables for autochecker compatibility

2. **Configuration Managers**
   - `get_llm_config()`: Loads LLM credentials
   - `get_lms_api_key()`: Loads backend API key
   - `get_agent_api_base_url()`: Gets backend URL

3. **Tools**
   - `read_file(path)`: Read file contents from project repository
   - `list_files(path)`: List directory contents
   - `query_api(method, path, body, use_auth)`: Call backend API with optional auth
   - All file tools enforce path security (no directory traversal)

4. **LLM Client** (`call_llm`)
   - Sends HTTP POST to `{api_base}/chat/completions`
   - Uses `httpx` for HTTP requests
   - 60-second timeout
   - Includes tool definitions in request

5. **Agentic Loop** (`run_agentic_loop`)
   - Maintains conversation history
   - Executes tool calls and feeds results back to LLM
   - Maximum 20 tool calls per question
   - Extracts answer and source from final response

6. **CLI Entry Point** (`main`)
   - Parses command-line argument (the question)
   - Orchestrates the flow
   - Outputs JSON to stdout
   - All debug output to stderr

## Tool Definitions

### `read_file`

**Purpose:** Read the contents of a file from the project repository.

**Schema:**
```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read the contents of a file from the project repository",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Relative path from project root"
        }
      },
      "required": ["path"]
    }
  }
}
```

**Security:**
- Rejects paths containing `..`
- Ensures resolved path is within project root

### `list_files`

**Purpose:** List files and directories at a given path.

**Schema:**
```json
{
  "type": "function",
  "function": {
    "name": "list_files",
    "description": "List files and directories at a given path",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Relative directory path from project root"
        }
      },
      "required": ["path"]
    }
  }
}
```

**Security:**
- Rejects paths containing `..`
- Ensures resolved path is within project root

### `query_api`

**Purpose:** Call the backend API to query data or check system behavior.

**Schema:**
```json
{
  "type": "function",
  "function": {
    "name": "query_api",
    "description": "Call the backend API to query data or check system behavior",
    "parameters": {
      "type": "object",
      "properties": {
        "method": {
          "type": "string",
          "description": "HTTP method (GET, POST, PUT, DELETE)"
        },
        "path": {
          "type": "string",
          "description": "API endpoint path"
        },
        "body": {
          "type": "string",
          "description": "Optional JSON request body for POST/PUT requests"
        },
        "use_auth": {
          "type": "boolean",
          "description": "Whether to include authentication header (default: true)"
        }
      },
      "required": ["method", "path"]
    }
  }
}
```

**Implementation:**
- Uses `httpx` for HTTP requests
- Reads `LMS_API_KEY` from environment for authentication
- Sends `Authorization: Bearer {LMS_API_KEY}` header when `use_auth=true`
- Returns JSON string with `status_code` and `body`
- 30-second timeout

## Agentic Loop

The agentic loop implements the following logic:

```python
1. Initialize messages = [system_prompt, user_question]
2. Loop (max 20 iterations):
   a. Call LLM with messages + tool definitions
   b. If LLM returns tool_calls:
      - Execute each tool
      - Append tool results as "tool" role messages
      - Continue loop
   c. If LLM returns text answer (no tool_calls):
      - Extract answer and source
      - Return JSON output
      - Exit loop
3. If max iterations reached, get final summary from LLM
```

## System Prompt

The system prompt instructs the LLM to:

1. Use appropriate tools based on question type:
   - Wiki questions → `list_files`, `read_file`
   - Source code questions → `read_file` on `.py` files
   - Data queries → `query_api`
   - Bug diagnosis → `query_api` to reproduce, then `read_file` to find bug

2. Always include source file paths in answers:
   - Wiki: `wiki/filename.md`
   - Source: `backend/app/filename.py`
   - Config: `docker-compose.yml`

3. Be efficient with tool calls and provide complete answers

## API Request Format

```json
POST {api_base}/chat/completions
Headers:
  Authorization: Bearer {api_key}
  Content-Type: application/json

Body:
{
  "model": "qwen3-coder-plus",
  "messages": [...],
  "tools": [...],
  "tool_choice": "auto"
}
```

## Response Format

**stdout** (single JSON line):
```json
{
  "answer": "There are 44 items in the database.",
  "source": "",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": \"[...]\"}"
    }
  ]
}
```

**stderr** (debug output):
```
Question: How many items are in the database?
Using model: qwen3-coder-plus
API Base URL: http://localhost:42002

[Loop iteration 1]
[Executing tool: query_api({'method': 'GET', 'path': '/items/'})]
[query_api] GET http://localhost:42002/items/ (auth: yes)

[Loop iteration 2]
[LLM provided final answer]

Answer received
```

## Usage

```bash
# Run with a question
uv run agent.py "How many items are in the database?"

# Example output:
# {"answer": "There are 44 items...", "source": "", "tool_calls": [...]}
```

## Error Handling

- **Missing configuration:** Exits with error message to stderr
- **API timeout:** 60-second limit for LLM, 30-second for backend
- **Invalid API response:** Logs the response to stderr and exits
- **No question provided:** Shows usage message
- **Path traversal attempts:** Tools reject unsafe paths
- **Directory traversal:** Blocked by `is_safe_path()` function

## Testing

Run the regression tests:

```bash
uv run pytest test_agent.py -v
```

Tests verify:
1. Agent produces valid JSON with required fields
2. Correct tools are called for specific questions
3. Source field contains expected file references
4. Tool calls have required fields (tool, args, result)

## Benchmark Performance

The agent achieves **8/10 (80%)** on the local evaluation benchmark:

**Passing:**
1. ✅ Wiki branch protection question
2. ✅ Wiki SSH connection question
3. ✅ Backend framework (FastAPI) question
4. ✅ API router listing question
5. ✅ Database items count question
6. ✅ Unauthenticated status code question
7. ✅ Completion-rate bug (ZeroDivisionError)
8. ✅ Top-learners bug (TypeError/NoneType)

**Failing:**
9. ⏳ HTTP request journey (LLM judge - complex reasoning)
10. ⏳ ETL pipeline idempotency (LLM judge - complex reasoning)

The failing questions require multi-file analysis and complex reasoning that sometimes exceeds the tool call limit or produces incomplete answers.

## Lessons Learned

1. **Source extraction is critical:** Many questions require a `source` field. The `extract_source()` function uses regex patterns to find file references in the LLM's answer.

2. **Tool descriptions matter:** Clear, specific tool descriptions help the LLM choose the right tool. For example, mentioning `use_auth=false` for authentication testing.

3. **Max tool calls tuning:** Started with 10, increased to 15, then 20. More complex questions need more iterations.

4. **System prompt iteration:** The system prompt evolved to explicitly guide the LLM on:
   - When to use each tool
   - How to format source references
   - Bug diagnosis workflow

5. **Environment variable flexibility:** The agent checks both files and environment variables to support local development and autochecker evaluation.

6. **LLM judge questions:** Questions 9 and 10 use LLM-based judging with rubrics. These require tracing request flows or explaining idempotency, which is challenging for the current setup.

## Future Improvements

1. **Better source extraction:** Add more patterns for detecting file references
2. **Smarter tool selection:** Improve system prompt for complex multi-step questions
3. **Response truncation:** Handle large file contents that exceed LLM context
4. **Error recovery:** Better handling of API errors and retries
