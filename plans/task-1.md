# Task 1 Plan: Call an LLM from Code

## LLM Provider and Model

**Provider:** Qwen Code API (self-hosted on VM via qwen-code-oai-proxy)

**Model:** `qwen3-coder-plus`

**Configuration:**
- API Key: stored in `.env.agent.secret` as `LLM_API_KEY`
- API Base: `http://10.93.24.214:42005/v1` (OpenAI-compatible endpoint)
- Model: `qwen3-coder-plus`

## Architecture

The agent will be a simple Python CLI script that:

1. **Parses command-line input** — takes the question as the first argument (`sys.argv[1]`)
2. **Loads environment variables** — reads `.env.agent.secret` for LLM credentials
3. **Calls the LLM API** — uses `httpx` (already in dependencies) to send a chat completion request
4. **Parses the response** — extracts the answer from the LLM response
5. **Outputs JSON** — prints a single JSON line to stdout with `answer` and `tool_calls` fields

## Data Flow

```
Command line → agent.py → Load .env → Build API request → httpx POST → LLM API
                                                              ↓
JSON output ← Format response ← Parse LLM response ← Receive response
```

## Implementation Details

### Environment Loading
- Use `pathlib` to locate `.env.agent.secret` in project root
- Parse simple `KEY=value` format manually (no extra dependencies)

### API Request
- Endpoint: `{LLM_API_BASE}/chat/completions`
- Method: POST
- Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
- Body:
  ```json
  {
    "model": "{LLM_MODEL}",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant. Answer questions concisely."},
      {"role": "user", "content": "<question>"}
    ]
  }
  ```

### Response Handling
- Extract `choices[0].message.content` from the response
- Format as JSON: `{"answer": "<content>", "tool_calls": []}`

### Error Handling
- Timeout: 60 seconds max for API call
- Exit code 0 on success, non-zero on error
- All debug output to stderr, only JSON to stdout

## Testing Strategy

Create one regression test that:
1. Runs `uv run agent.py "What is 2+2?"` as subprocess
2. Parses stdout as JSON
3. Asserts `answer` field exists
4. Asserts `tool_calls` field exists and is an array

## Files to Create

1. `plans/task-1.md` — this plan
2. `agent.py` — the main CLI agent
3. `AGENT.md` — documentation
4. `backend/tests/unit/test_agent_task1.py` — regression test
