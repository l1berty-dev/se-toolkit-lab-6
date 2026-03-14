# Agent Architecture

## Overview

This agent is a Python CLI that connects to an LLM via an OpenAI-compatible API and returns structured JSON answers. It implements an **agentic loop** with tools (`read_file`, `list_files`) to explore the project wiki and find accurate answers.

## LLM Provider

**Provider:** Qwen Code API (self-hosted via qwen-code-oai-proxy on a VM)

**Model:** `qwen3-coder-plus`

**Why Qwen Code:**
- 1000 free requests per day
- Available in Russia
- No credit card required
- OpenAI-compatible API with tool calling support

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
   - Parses `.env.agent.secret` file
   - Simple KEY=value format (no external dependencies)

2. **Configuration Manager** (`get_llm_config`)
   - Validates that all required variables are present
   - Exits with error if configuration is missing

3. **Tools**
   - `read_file(path)`: Read file contents from project repository
   - `list_files(path)`: List directory contents
   - Both tools enforce path security (no directory traversal)

4. **LLM Client** (`call_llm`)
   - Sends HTTP POST to `{api_base}/chat/completions`
   - Uses `httpx` for HTTP requests
   - 60-second timeout
   - Includes tool definitions in request

5. **Agentic Loop** (`run_agentic_loop`)
   - Maintains conversation history
   - Executes tool calls and feeds results back to LLM
   - Maximum 10 tool calls per question
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

## Agentic Loop

The agentic loop implements the following logic:

```python
1. Initialize messages = [system_prompt, user_question]
2. Loop (max 10 iterations):
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

1. Use `list_files` to discover wiki files when unsure where to look
2. Use `read_file` to read relevant files
3. Always include a source reference in the final answer
4. Format source as: `wiki/filename.md#section-anchor`

```
You are a helpful assistant with access to a project wiki.

You have two tools:
- list_files(path): List files in a directory
- read_file(path): Read the contents of a file

When answering questions about the project:
1. First use list_files("wiki") to discover available documentation
2. Use read_file() to read relevant files and find accurate information
3. Include the source file path and section in your final answer
4. Format source as: wiki/filename.md#section-anchor

Think step-by-step and use your tools to find accurate answers from the wiki.
```

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
    {"role": "system", "content": "..."},
    {"role": "user", "content": "<question>"}
  ],
  "tools": [...],
  "tool_choice": "auto"
}
```

## Response Format

**stdout** (single JSON line):
```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "..."
    }
  ]
}
```

**stderr** (debug output):
```
Question: How do you resolve a merge conflict?
Using model: qwen3-coder-plus

[Loop iteration 1]
[Executing tool: list_files({'path': 'wiki'})]

[Loop iteration 2]
[Executing tool: read_file({'path': 'wiki/git-workflow.md'})]

[Loop iteration 3]
[LLM provided final answer]

Answer received
Source: wiki/git-workflow.md#resolving-merge-conflict
```

## Usage

```bash
# Run with a question
uv run agent.py "How do you resolve a merge conflict?"

# Example output:
# {"answer": "...", "source": "wiki/git-workflow.md#...", "tool_calls": [...]}
```

## Error Handling

- **Missing configuration:** Exits with error message to stderr
- **API timeout:** 60-second limit, exits on timeout
- **Invalid API response:** Logs the response to stderr and exits
- **No question provided:** Shows usage message
- **Path traversal attempts:** Tools reject unsafe paths

## Testing

Run the regression tests:

```bash
uv run pytest test_agent.py -v
```

Tests verify:
1. Agent produces valid JSON with required fields
2. Correct tools are called for specific questions
3. Source field contains expected file references

## Future Extensions (Task 3)

- Add `query_api` tool for backend LMS queries
- Expand system prompt for domain-specific knowledge
- Improve source extraction with better section anchor detection
