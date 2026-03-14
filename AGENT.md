# Agent Architecture

## Overview

This project implements a CLI agent (`agent.py`) that connects to an LLM API to answer user questions. The agent has **tools** (`read_file`, `list_files`, `query_api`) that allow it to navigate the project wiki, read source code, and query the running backend API. This enables the agent to answer questions about documentation, system architecture, and live data.

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
                    │  - query_api     │
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
3. Loads backend API configuration from `.env.docker.secret`
4. Runs an **agentic loop**:
   - Sends the question to the LLM with a system prompt
   - Parses the LLM's JSON response for tool calls
   - Executes tools and feeds results back to the LLM
   - Repeats until the LLM provides a final answer
5. Returns a structured JSON response with `answer`, `source`, and `tool_calls`

**Input:**
```bash
uv run agent.py "How many items are in the database?"
```

**Output:**
```json
{
  "answer": "There are 44 items in the database.",
  "source": "",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": [...]}"
    }
  ]
}
```

### Configuration Files

The agent reads from two environment files:

#### `.env.agent.secret` (LLM Configuration)

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for LLM authentication | `sk-...` |
| `LLM_API_BASE` | Base URL of the LLM API | `http://vm-ip:port/v1` |
| `LLM_MODEL` | Model name to use | `qwen3-coder-plus` |

#### `.env.docker.secret` (Backend Configuration)

| Variable | Description | Example |
|----------|-------------|---------|
| `LMS_API_KEY` | API key for backend authentication | `my-secret-key` |
| `AGENT_API_BASE_URL` | Base URL for query_api (optional) | `http://localhost:42001` |

**Note:** `AGENT_API_BASE_URL` can also be set as an environment variable (highest priority) or defaults to `http://localhost:42001`.

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

### `query_api`

Calls the backend API to retrieve system information or data.

**Parameters:**
- `method` (string, required): HTTP method (GET, POST, PUT, DELETE)
- `path` (string, required): API path (e.g., `/items/`, `/analytics/scores`)
- `body` (string, optional): JSON request body for POST/PUT requests
- `auth` (boolean, optional): Whether to include authentication header (default: `true`)

**Returns:** JSON string with `status_code` and `body`, or error message.

**Authentication:**
- Uses `LMS_API_KEY` from `.env.docker.secret`
- Include `Authorization: Bearer {LMS_API_KEY}` header when `auth=true`
- Use `auth=false` to test unauthenticated access (e.g., check 401/403 responses)

## Agentic Loop

The agentic loop enables multi-turn reasoning with the LLM:

1. **Initialize** conversation with system prompt + user question
2. **Call LLM** (timeout: 120s) and get response
3. **Parse response:**
   - If `{"tool": "...", "args": {...}}` → execute tool, append result to conversation, go to step 2
   - If `{"answer": "...", "source": "..."}` → return final answer
4. **Limit:** Maximum 20 tool calls per question (prevents infinite loops)

### System Prompt Strategy

The system prompt guides the LLM to choose the right tool:

```
You have three tools:
1. list_files - List files in a directory (use to discover wiki files or source code)
2. read_file - Read the contents of a file (wiki docs, source code, config files)
3. query_api - Call the running backend API (for data queries, status codes, errors)

To answer questions:
- For wiki/documentation questions: use list_files to discover wiki files, then read_file
- For source code questions: use list_files on backend/app/routers, then read_file
- For data queries (item count, scores): use query_api with GET
- For HTTP status codes: use query_api with auth=false to see 401/403
- For API error diagnosis: use query_api to see the error, then read_file to find the bug
```

### Message Flow Example

```
User: "How many items are in the database?"

→ LLM: {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}}
→ Execute query_api → result="{\"status_code\": 200, \"body\": [...]}"
→ Append result to conversation

→ LLM: {"answer": "There are 44 items...", "source": ""}
→ Output JSON with answer, source, and tool_calls
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
| `source` | string | Wiki section reference (optional for system questions) |
| `tool_calls` | array | List of all tool calls made during the agentic loop |

### Tool Call Entry

| Field | Type | Description |
|-------|------|-------------|
| `tool` | string | Name of the tool executed |
| `args` | object | Arguments passed to the tool |
| `result` | string | Tool output (file contents, directory listing, or API response) |

## Data Flow

1. **Input Parsing:** The question is read from `sys.argv[1]`
2. **Configuration Loading:**
   - `.env.agent.secret` → LLM credentials
   - `.env.docker.secret` → Backend API credentials
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
| API timeout (>120s) | Exit with error to stderr, code 1 |
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
# Copy and configure environment files
cp .env.agent.example .env.agent.secret
cp .env.docker.example .env.docker.secret

# Edit files with your credentials

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
uv run pytest test_agent.py -v
```

Tests verify:
- Valid JSON output with required fields
- Tool calls are populated when tools are used
- Source field correctly identifies wiki sections
- `query_api` tool works for system questions

## Benchmark Results

The agent passes all 10 local evaluation questions in `run_eval.py`:

| # | Question | Tool(s) | Status |
|---|----------|---------|--------|
| 0 | Protect a branch on GitHub? | `read_file` | ✅ |
| 1 | SSH connection steps? | `read_file` | ✅ |
| 2 | What Python web framework? | `read_file` | ✅ |
| 3 | List API router modules? | `list_files` | ✅ |
| 4 | How many items in database? | `query_api` | ✅ |
| 5 | Status code without auth? | `query_api` | ✅ |
| 6 | /analytics/completion-rate error? | `query_api`, `read_file` | ✅ |
| 7 | /analytics/top-learners crash? | `query_api`, `read_file` | ✅ |
| 8 | Request journey (docker-compose)? | `read_file` | ✅ |
| 9 | ETL idempotency? | `read_file` | ✅ |

## Lessons Learned

### Tool Design

1. **Explicit parameter names matter:** Initially, the LLM called `query_api` with wrong parameter names like `endpoint` instead of `path`. Adding clear examples in the system prompt fixed this.

2. **Optional parameters need defaults:** The `auth` parameter for `query_api` was added to support testing unauthenticated access. Setting a default of `true` ensures backward compatibility.

3. **Path hints help:** Adding a list of common paths (e.g., `backend/app/routers/`, `backend/app/etl.py`) in the system prompt reduced the number of tool calls needed to find files.

### Agentic Loop

1. **Timeout tuning:** Complex questions (like the request journey) require reading multiple files. Increasing the timeout from 60s to 120s and max tool calls from 10 to 20 prevented timeouts.

2. **JSON parsing robustness:** The LLM sometimes returns extra text around the JSON. Using regex patterns to extract tool calls and answer objects improved reliability.

3. **Conversation context:** Appending tool results as user messages (rather than tool role messages) improved compatibility with the Qwen API.

### Benchmark Iteration

1. **Run questions individually:** When debugging, use `uv run run_eval.py --index N` to test a single question. This is faster and helps isolate issues.

2. **Rate limiting:** Running the full benchmark multiple times in quick succession can cause rate limiting. Wait between runs if you see unexpected timeouts.

3. **LLM consistency:** The same question may succeed or fail depending on the LLM's mood. If a question fails intermittently, try improving the system prompt rather than tweaking the code.

## Files

| File | Description |
|------|-------------|
| `agent.py` | Main CLI entry point with agentic loop |
| `.env.agent.secret` | LLM configuration (gitignored) |
| `.env.docker.secret` | Backend API configuration (gitignored) |
| `plans/task-1.md` | Task 1 implementation plan |
| `plans/task-2.md` | Task 2 implementation plan |
| `plans/task-3.md` | Task 3 implementation plan |
| `AGENT.md` | This documentation |
| `test_agent.py` | Regression tests |
