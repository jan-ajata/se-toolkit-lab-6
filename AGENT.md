# Agent Architecture

## Overview

This project implements a CLI agent (`agent.py`) that connects to an LLM API to answer user questions. The agent has **tools** (`read_file`, `list_files`) that allow it to navigate and read the project wiki, then reason about the results to provide accurate answers with source references.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Command Line   │────▶│   agent.py   │────▶│   LLM API       │
│  (question)     │     │  (CLI tool)  │     │  (Qwen Code)    │
└─────────────────┘     └──────────────┘     └─────────────────┘
                               │                      │
                               │◀─────────────────────┘
                               ▼
                    ┌──────────────────┐
                    │  Tool Execution  │
                    │  - read_file     │
                    │  - list_files    │
                    └──────────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  JSON Output │
                        │  (stdout)    │
                        └──────────────┘
```

## Components

### `agent.py`

The main CLI entry point that:
1. Parses command-line arguments (the user's question)
2. Loads LLM configuration from `.env.agent.secret`
3. Runs an **agentic loop**:
   - Sends the question to the LLM with a system prompt
   - Parses the LLM's JSON response for tool calls
   - Executes tools and feeds results back to the LLM
   - Repeats until the LLM provides a final answer
4. Returns a structured JSON response with `answer`, `source`, and `tool_calls`

**Input:**
```bash
uv run agent.py "How do you resolve a merge conflict?"
```

**Output:**
```json
{
  "answer": "To resolve a merge conflict, edit the file...",
  "source": "wiki/git-vscode.md#resolve-a-merge-conflict",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."},
    {"tool": "read_file", "args": {"path": "wiki/git-vscode.md"}, "result": "..."}
  ]
}
```

### Configuration (`.env.agent.secret`)

The agent reads the following environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for authentication | `sk-...` |
| `LLM_API_BASE` | Base URL of the LLM API | `http://vm-ip:port/v1` |
| `LLM_MODEL` | Model name to use | `qwen3-coder-plus` |

## Tools

### `read_file`

Reads the contents of a file from the project repository.

**Parameters:**
- `path` (string, required): Relative path from project root (e.g., `wiki/git-workflow.md`)

**Returns:** File contents as a string, or an error message.

**Security:**
- Rejects absolute paths
- Rejects paths containing `..` (directory traversal)
- Ensures the resolved path is within the project root

### `list_files`

Lists files and directories at a given path.

**Parameters:**
- `path` (string, required): Relative directory path from project root (e.g., `wiki`)

**Returns:** Newline-separated listing of entries, or an error message.

**Security:** Same as `read_file`

## Agentic Loop

The agentic loop enables multi-turn reasoning with the LLM:

1. **Initialize** conversation with system prompt + user question
2. **Call LLM** and get JSON response
3. **Parse response:**
   - If `{"tool": "...", "args": {...}}` → execute tool, append result to conversation, go to step 2
   - If `{"answer": "...", "source": "..."}` → return final answer
4. **Limit:** Maximum 10 tool calls per question (prevents infinite loops)

### Message Flow Example

```
User: "How do you resolve a merge conflict?"

→ LLM: {"tool": "list_files", "args": {"path": "wiki"}}
→ Execute list_files → result="git-workflow.md\ngit.md\n..."
→ Append result to conversation

→ LLM: {"tool": "read_file", "args": {"path": "wiki/git-vscode.md"}}
→ Execute read_file → result="# Git in VS Code\n..."
→ Append result to conversation

→ LLM: {"answer": "To resolve...", "source": "wiki/git-vscode.md#resolve-a-merge-conflict"}
→ Output JSON with answer, source, and tool_calls
```

## System Prompt Strategy

The system prompt instructs the LLM to:

1. Use `list_files` to discover relevant wiki files
2. Use `read_file` to read the contents of specific files
3. Find the answer and identify the specific section (for the `source` field)
4. Always respond with valid JSON

Example system prompt excerpt:
```
To call a tool, respond with:
{"tool": "tool_name", "args": {"param": "value"}}

For the final answer, respond with:
{"answer": "your answer", "source": "wiki/file.md#section"}
```

## Output Format

```json
{
  "answer": "The answer text from the LLM",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\ngit.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "# Git workflow\n..."
    }
  ]
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's answer to the question |
| `source` | string | Wiki section reference (e.g., `wiki/file.md#section`) |
| `tool_calls` | array | List of all tool calls made during the agentic loop |

### Tool Call Entry

| Field | Type | Description |
|-------|------|-------------|
| `tool` | string | Name of the tool executed |
| `args` | object | Arguments passed to the tool |
| `result` | string | Tool output (file contents or directory listing) |

## Data Flow

1. **Input Parsing:** The question is read from `sys.argv[1]`
2. **Configuration Loading:** `.env.agent.secret` is parsed for API credentials
3. **Agentic Loop:**
   - Build conversation context with system prompt + user question + tool results
   - Call LLM API via HTTP POST
   - Parse JSON response for tool calls or final answer
   - Execute tools with path validation
   - Append tool results to conversation
   - Repeat until final answer or max tool calls
4. **Output Formatting:** Return JSON with `answer`, `source`, and `tool_calls`

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing `.env.agent.secret` | Exit with error to stderr, code 1 |
| Missing config variables | Exit with error to stderr, code 1 |
| Network error | Exit with error to stderr, code 1 |
| API timeout (>60s) | Exit with error to stderr, code 1 |
| Invalid API response | Exit with error to stderr, code 1 |
| Missing question argument | Print usage to stderr, exit code 1 |
| Path traversal attempt | Tool returns error message, loop continues |
| Max tool calls reached | Final LLM call with gathered context |

## Output Conventions

- **stdout:** Only valid JSON (for programmatic consumption)
- **stderr:** All debug, progress, and error messages

This separation allows the agent to be used in pipelines and automated testing.

## Usage

### Basic Usage

```bash
# Copy and configure environment file
cp .env.agent.example .env.agent.secret
# Edit .env.agent.secret with your credentials

# Run the agent
uv run agent.py "How do you resolve a merge conflict?"
```

### Expected Output

```json
{
  "answer": "To resolve a merge conflict, open the file with conflict markers...",
  "source": "wiki/git-vscode.md#resolve-a-merge-conflict",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."},
    {"tool": "read_file", "args": {"path": "wiki/git-vscode.md"}, "result": "..."}
  ]
}
```

## Testing

Run the regression tests:

```bash
uv run pytest backend/tests/unit/test_agent.py -v
```

Tests verify:
- Valid JSON output with required fields
- Tool calls are populated when tools are used
- Source field correctly identifies wiki sections

## Files

| File | Description |
|------|-------------|
| `agent.py` | Main CLI entry point with agentic loop |
| `.env.agent.secret` | LLM configuration (gitignored) |
| `plans/task-1.md` | Task 1 implementation plan |
| `plans/task-2.md` | Task 2 implementation plan |
| `AGENT.md` | This documentation |
| `backend/tests/unit/test_agent.py` | Regression tests |
