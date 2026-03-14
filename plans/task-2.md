# Task 2 Plan: The Documentation Agent

## Overview

This task extends the Task 1 agent with two tools (`read_file`, `list_files`) and an agentic loop that allows the LLM to iteratively explore the wiki and find answers.

## Tool Definitions

### `read_file`

**Purpose:** Read the contents of a file from the project repository.

**Schema:**
```json
{
  "name": "read_file",
  "description": "Read the contents of a file from the project repository",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')"
      }
    },
    "required": ["path"]
  }
}
```

**Implementation:**
- Use `pathlib.Path` to read file contents
- Security: Reject paths containing `..` to prevent directory traversal
- Security: Ensure the resolved path is within the project root
- Return file contents as string, or error message if file doesn't exist

### `list_files`

**Purpose:** List files and directories at a given path.

**Schema:**
```json
{
  "name": "list_files",
  "description": "List files and directories at a given path",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative directory path from project root (e.g., 'wiki')"
      }
    },
    "required": ["path"]
  }
}
```

**Implementation:**
- Use `pathlib.Path.iterdir()` to list directory contents
- Security: Reject paths containing `..` to prevent directory traversal
- Security: Ensure the resolved path is within the project root
- Return newline-separated list of entry names

## Agentic Loop

The agentic loop implements the following logic:

```
1. Initialize messages list with system + user question
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
3. If max iterations reached, return best available answer
```

## Message Format

The conversation history will be maintained as:

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # Tool calls and results are appended here:
    # {"role": "assistant", "tool_calls": [...]},
    # {"role": "tool", "content": result, "tool_call_id": "..."},
]
```

## System Prompt

The system prompt will instruct the LLM to:

1. Use `list_files` to discover wiki files when unsure where to look
2. Use `read_file` to read relevant files
3. Always include a source reference in the final answer (file path + section anchor)
4. Be concise and accurate
5. Use tools iteratively until confident in the answer

Example:
```
You are a helpful assistant with access to a project wiki.

You have two tools:
- list_files(path): List files in a directory
- read_file(path): Read the contents of a file

When answering questions:
1. First use list_files("wiki") to discover available documentation
2. Use read_file() to read relevant files
3. Include the source file path and section in your answer
4. Format source as: wiki/filename.md#section-anchor

Always think step-by-step and use your tools to find accurate answers.
```

## Path Security

To prevent directory traversal attacks:

```python
def is_safe_path(base: Path, requested: Path) -> bool:
    """Check if requested path is within base directory."""
    try:
        # Resolve to absolute paths
        base_resolved = base.resolve()
        requested_resolved = (base / requested).resolve()
        # Check if requested is under base
        return requested_resolved.is_relative_to(base_resolved)
    except ValueError:
        return False
```

Reject any path containing `..` or that resolves outside the project root.

## Output Format

The final JSON output will include:

```json
{
  "answer": "The answer text from the LLM",
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

## Testing Strategy

Create 2 regression tests:

1. **Test merge conflict question:**
   - Question: "How do you resolve a merge conflict?"
   - Expected: `read_file` in tool_calls, `wiki/git-workflow.md` in source

2. **Test wiki listing question:**
   - Question: "What files are in the wiki?"
   - Expected: `list_files` in tool_calls

Tests will verify:
- Correct tools are called
- Source field contains expected file reference
- Answer is non-empty

## Files to Modify/Create

1. `plans/task-2.md` — this plan
2. `agent.py` — add tools and agentic loop
3. `AGENT.md` — update documentation
4. `test_agent.py` — add 2 regression tests
