# Task 3 Plan: The System Agent

## Overview

Extend the Task 2 agent with a `query_api` tool that can call the deployed backend API. This enables the agent to answer questions about the running system (framework, ports, status codes) and data-dependent queries (item count, scores).

## New Tool: `query_api`

### Purpose

Call the deployed backend API to retrieve system information or data.

### Parameters

- `method` (string, required): HTTP method (GET, POST, PUT, DELETE, etc.)
- `path` (string, required): API path (e.g., `/items/`, `/analytics/scores`)
- `body` (string, optional): JSON request body for POST/PUT requests

### Returns

JSON string with:
- `status_code`: HTTP status code
- `body`: Response body as JSON or text

### Authentication

The tool must authenticate using `LMS_API_KEY` from `.env.docker.secret`:
- Read `LMS_API_KEY` from environment
- Include in request header: `Authorization: Bearer {LMS_API_KEY}`

## Environment Variables

The agent must read all configuration from environment variables:

| Variable | Purpose | Source | Default |
|----------|---------|--------|---------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | - |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` | - |
| `LLM_MODEL` | Model name | `.env.agent.secret` | - |
| `LMS_API_KEY` | Backend API key for `query_api` | `.env.docker.secret` | - |
| `AGENT_API_BASE_URL` | Base URL for `query_api` | `.env.docker.secret` or env | `http://localhost:42002` |

**Important:** The autochecker injects different values at runtime. Never hardcode these values.

## Implementation Steps

### 1. Add `query_api` tool function

```python
def tool_query_api(method: str, path: str, body: str = None) -> str:
    """Call the backend API and return the response."""
    # Read LMS_API_KEY from environment
    # Build URL from AGENT_API_BASE_URL + path
    # Make HTTP request with Authorization header
    # Return JSON string with status_code and body
```

### 2. Register tool schema

Add to `TOOLS_SCHEMA`:
```json
{
  "type": "function",
  "function": {
    "name": "query_api",
    "description": "Call the backend API to query system data or status",
    "parameters": {
      "type": "object",
      "properties": {
        "method": {"type": "string", "description": "HTTP method (GET, POST, etc.)"},
        "path": {"type": "string", "description": "API path (e.g., /items/)"},
        "body": {"type": "string", "description": "JSON request body (optional)"}
      },
      "required": ["method", "path"]
    }
  }
}
```

### 3. Update system prompt

The system prompt should guide the LLM to choose the right tool:

```
You have three tools:
1. list_files - Discover files in directories like 'wiki' or 'backend'
2. read_file - Read file contents (wiki docs, source code)
3. query_api - Call the running backend API

Use wiki tools for documentation questions.
Use read_file on source code for framework/architecture questions.
Use query_api for:
  - Current data (item count, scores)
  - HTTP status codes
  - API error diagnosis
```

### 4. Update output format

The `source` field is now optional since system questions may not have a wiki source:

```json
{
  "answer": "There are 120 items in the database.",
  "source": "",  // Optional for system questions
  "tool_calls": [...]
}
```

## Benchmark Questions

The agent must pass 10 local questions:

| # | Question | Expected Tool | Expected Answer |
|---|----------|---------------|-----------------|
| 0 | Protect a branch on GitHub? | `read_file` | branch, protect |
| 1 | SSH connection steps? | `read_file` | ssh/key/connect |
| 2 | What Python web framework? | `read_file` | FastAPI |
| 3 | List API router modules? | `list_files` | items, interactions, analytics, pipeline |
| 4 | How many items in database? | `query_api` | number > 0 |
| 5 | Status code for /items/ without auth? | `query_api` | 401/403 |
| 6 | /analytics/completion-rate error? | `query_api`, `read_file` | ZeroDivisionError |
| 7 | /analytics/top-learners crash? | `query_api`, `read_file` | TypeError/None |
| 8 | Request journey (docker-compose + Dockerfile)? | `read_file` | Caddy→FastAPI→auth→router→ORM→PostgreSQL |
| 9 | ETL idempotency? | `read_file` | external_id check |

## Iteration Strategy

1. Implement `query_api` tool
2. Run `uv run run_eval.py`
3. For each failure:
   - Check which tool was called (or not called)
   - Check if the answer matches expected keywords
   - Adjust system prompt or tool descriptions
4. Repeat until all 10 pass

## Files to Modify

1. `plans/task-3.md` - This plan
2. `agent.py` - Add `query_api` tool, update system prompt
3. `AGENT.md` - Document `query_api` and lessons learned
4. `test_agent.py` - Add 2 system agent regression tests

## Acceptance Criteria Checklist

- [x] Plan created before code
- [x] `query_api` tool defined with correct schema
- [x] `query_api` authenticates with `LMS_API_KEY`
- [x] Agent reads all config from environment variables
- [x] Agent reads `AGENT_API_BASE_URL` (defaults to `http://localhost:42001`)
- [x] Static system questions answered correctly
- [x] Data-dependent questions answered correctly
- [x] `run_eval.py` passes all 10 questions
- [x] `AGENT.md` has 200+ words on architecture and lessons (1742 words)
- [x] 2 new regression tests pass (7 total tests)
- [x] Autochecker bot benchmark passes

## Benchmark Results

**Initial Score:** 6/10

**First Failures:**
- Question 4: Agent didn't know the path to backend routers → Added path hints to system prompt
- Question 6: query_api always sent auth header → Added `auth` parameter
- Question 7-8: Timeouts → Increased max tool calls to 20, timeout to 120s
- Question 9: LLM returned tool call instead of answer → Improved JSON parsing

**Iteration Strategy:**
1. Run individual questions with `--index N` to isolate failures
2. Add explicit examples in system prompt for each tool
3. Increase timeouts for complex reasoning questions
4. Make `auth` parameter optional for testing unauthenticated access

**Final Score:** 10/10 PASSED
