# Task 2 Plan: The Documentation Agent

## Overview

Extend the Task 1 agent with tools (`read_file`, `list_files`) and an agentic loop that allows the LLM to iteratively query the project wiki to find answers.

## Tool Definitions

### `read_file`

**Purpose:** Read the contents of a file from the project repository.

**Parameters:**
- `path` (string, required): Relative path from project root (e.g., `wiki/git-workflow.md`)

**Returns:** File contents as a string, or an error message if the file doesn't exist.

**Security:**
- Resolve the path against the project root
- Reject paths containing `..` (directory traversal)
- Reject absolute paths
- Ensure the resolved path is within the project directory

### `list_files`

**Purpose:** List files and directories at a given path.

**Parameters:**
- `path` (string, required): Relative directory path from project root (e.g., `wiki`)

**Returns:** Newline-separated listing of entries (files and directories).

**Security:**
- Same path validation as `read_file`
- Only list directories, not files

## Tool Schema (OpenAI Function Calling)

Tools will be defined as JSON schemas in the `tools` parameter of the chat completions API:

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read a file from the project repository",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string", "description": "Relative path from project root"}
      },
      "required": ["path"]
    }
  }
}
```

## Agentic Loop

The loop will:

1. **Initialize** conversation with system prompt + user question
2. **Call LLM** with tool definitions
3. **Check response:**
   - If `tool_calls` present:
     - Execute each tool call
     - Append tool results as `tool` role messages
     - Loop back to step 2
   - If no `tool_calls` (final answer):
     - Extract answer from response
     - Output JSON and exit
4. **Limit:** Maximum 10 tool calls per question (prevent infinite loops)

### Message Flow Example

```
User: "How do you resolve a merge conflict?"

→ LLM (with tools): tool_calls=[read_file(path="wiki/git-workflow.md")]
→ Execute read_file → result="..."
→ Send result back to LLM as tool role

→ LLM: tool_calls=[read_file(path="wiki/git.md")]
→ Execute read_file → result="..."
→ Send result back to LLM as tool role

→ LLM: "To resolve a merge conflict, edit the file..." (no tool_calls)
→ Output JSON with answer and source
```

## System Prompt Strategy

The system prompt will instruct the LLM to:

1. Use `list_files` to discover relevant wiki files
2. Use `read_file` to read the contents of specific files
3. Find the answer and identify the specific section (for the `source` field)
4. Return the final answer with a source reference in the format: `wiki/filename.md#section-anchor`

Example system prompt:
```
You are a documentation assistant. You have access to a project wiki.
Use list_files to discover wiki files, then read_file to find answers.
Always cite your source using the file path and section anchor.
Format: wiki/filename.md#section-anchor
```

## Output Format

```json
{
  "answer": "The answer text from the LLM",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
  ]
}
```

## Path Security Implementation

```python
def validate_path(path: str) -> Path:
    """Validate and resolve a relative path against project root."""
    # Reject absolute paths
    if os.path.isabs(path):
        raise ValueError("Absolute paths not allowed")
    
    # Reject directory traversal
    if ".." in path:
        raise ValueError("Directory traversal not allowed")
    
    # Resolve against project root
    project_root = Path(__file__).parent
    full_path = (project_root / path).resolve()
    
    # Ensure path is within project root
    if not str(full_path).startswith(str(project_root)):
        raise ValueError("Path outside project root")
    
    return full_path
```

## Files to Modify/Create

1. `plans/task-2.md` - This plan (create first)
2. `agent.py` - Add tools and agentic loop
3. `AGENT.md` - Update documentation
4. `backend/tests/unit/test_agent.py` - Add 2 tool-calling tests

## Acceptance Criteria Checklist

- [ ] Plan created before code
- [ ] `read_file` tool implemented with path security
- [ ] `list_files` tool implemented with path security
- [ ] Agentic loop executes tool calls and feeds results back
- [ ] `tool_calls` populated in output
- [ ] `source` field correctly identifies wiki section
- [ ] Maximum 10 tool calls enforced
- [ ] 2 regression tests pass
- [ ] AGENT.md updated
