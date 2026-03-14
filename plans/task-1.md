# Task 1 Plan: Call an LLM from Code

## LLM Provider and Model

**Provider:** Qwen Code API (OpenAI-compatible endpoint)
**Model:** `coder-model`

**Rationale:**
- 1000 free requests per day (sufficient for development and testing)
- Available in Russia without restrictions
- No credit card required
- Strong tool-calling capabilities (needed for future tasks)
- OpenAI-compatible API (easy integration with standard libraries)

## Configuration

The agent will read configuration from `.env.agent.secret`:
- `LLM_API_KEY` - API key for authentication
- `LLM_API_BASE` - Base URL for the API endpoint
- `LLM_MODEL` - Model name to use

## Agent Architecture

### Input
- Command-line argument: the user's question (string)
- Example: `uv run agent.py "What does REST stand for?"`

### Processing Flow
1. Parse command-line argument (the question)
2. Load environment configuration from `.env.agent.secret`
3. Construct HTTP POST request to the LLM API:
   - Endpoint: `{LLM_API_BASE}/chat/completions`
   - Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
   - Body: JSON with `model`, `messages` (system + user), and `temperature`
4. Send request with 60-second timeout
5. Parse the JSON response and extract the assistant's answer
6. Format output as JSON with required fields

### Output
Single JSON line to stdout:
```json
{"answer": "<LLM response>", "tool_calls": []}
```

**Important:** All debug/logging output goes to stderr, only the final JSON goes to stdout.

## Error Handling

- **Missing config:** Exit with error message to stderr, non-zero exit code
- **API error (network/timeout):** Exit with error message to stderr, non-zero exit code
- **Invalid API response:** Exit with error message to stderr, non-zero exit code
- **Missing question argument:** Print usage to stderr, exit with non-zero code

## Dependencies

- `httpx` - HTTP client (already in project dependencies via `pyproject.toml`)
- `pydantic-settings` - For loading environment variables (already available)
- Standard library: `json`, `sys`, `os`, `argparse`

## Testing Strategy

Create one regression test that:
1. Runs `agent.py` as a subprocess with a test question
2. Parses stdout as JSON
3. Asserts `answer` field exists and is non-empty
4. Asserts `tool_calls` field exists and is an array

## Files to Create

1. `plans/task-1.md` - This plan
2. `agent.py` - The CLI agent
3. `AGENT.md` - Documentation
4. `backend/tests/unit/test_agent.py` (or similar) - Regression test

## Acceptance Criteria Checklist

- [ ] Plan created before code
- [ ] `agent.py` outputs valid JSON with `answer` and `tool_calls`
- [ ] API key loaded from `.env.agent.secret` (not hardcoded)
- [ ] All debug output to stderr
- [ ] Exit code 0 on success
- [ ] 60-second timeout enforced
- [ ] One passing regression test
