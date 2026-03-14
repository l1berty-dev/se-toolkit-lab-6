# Agent Architecture

## Overview

This agent is a Python CLI that connects to an LLM via an OpenAI-compatible API and returns structured JSON answers. It forms the foundation for the more advanced agents built in Tasks 2-3.

## LLM Provider

**Provider:** Qwen Code API (self-hosted via qwen-code-oai-proxy on a VM)

**Model:** `qwen3-coder-plus`

**Why Qwen Code:**
- 1000 free requests per day
- Available in Russia
- No credit card required
- OpenAI-compatible API

## Configuration

The agent reads configuration from `.env.agent.secret` in the project root:

```
LLM_API_KEY=<your-api-key>
LLM_API_BASE=http://<vm-ip>:<port>/v1
LLM_MODEL=qwen3-coder-plus
```

## Architecture

### Data Flow

```
┌─────────────┐     ┌──────────┐     ┌─────────────┐     ┌──────────┐
│  Command    │────▶│ agent.py │────▶│  LLM API    │────▶│  JSON    │
│  Question   │     │  CLI     │     │  (Qwen)     │     │  Output  │
└─────────────┘     └──────────┘     └─────────────┘     └──────────┘
```

### Components

1. **Environment Loader** (`load_env`)
   - Parses `.env.agent.secret` file
   - Simple KEY=value format (no external dependencies)

2. **Configuration Manager** (`get_llm_config`)
   - Validates that all required variables are present
   - Exits with error if configuration is missing

3. **LLM Client** (`call_llm`)
   - Sends HTTP POST to `{api_base}/chat/completions`
   - Uses `httpx` for async-capable HTTP requests
   - 60-second timeout
   - Extracts answer from `choices[0].message.content`

4. **CLI Entry Point** (`main`)
   - Parses command-line argument (the question)
   - Orchestrates the flow
   - Outputs JSON to stdout
   - All debug output to stderr

## API Request Format

```json
POST {api_base}/chat/completions
Headers:
  Authorization: Bearer {api_key}
  Content-Type: application/json

Body:
{
  "model": "qwen3-coder-plus",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant. Answer questions concisely and accurately."
    },
    {
      "role": "user",
      "content": "<question>"
    }
  ]
}
```

## Response Format

**stdout** (single JSON line):
```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

**stderr** (debug output):
```
Question: What does REST stand for?
Using model: qwen3-coder-plus
Calling LLM API at http://.../v1/chat/completions...
Answer received
```

## Usage

```bash
# Run with a question
uv run agent.py "What does REST stand for?"

# Expected output:
# {"answer": "Representational State Transfer.", "tool_calls": []}
```

## Error Handling

- **Missing configuration:** Exits with error message to stderr
- **API timeout:** 60-second limit, exits on timeout
- **Invalid API response:** Logs the response to stderr and exits
- **No question provided:** Shows usage message

## Testing

Run the regression test:

```bash
uv run pytest backend/tests/unit/test_agent_task1.py -v
```

The test verifies:
1. Agent produces valid JSON
2. `answer` field is present
3. `tool_calls` field is present and is an array

## Future Extensions (Tasks 2-3)

- **Task 2:** Add `read_file` and `list_files` tools for documentation lookup
- **Task 3:** Add `query_api` tool for backend LMS queries and expand the agentic loop
