# Agent Architecture

## Overview

This project implements a CLI agent (`agent.py`) that connects to an LLM API to answer user questions. The agent serves as the foundation for more advanced features (tools, agentic loop) that will be added in subsequent tasks.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Command Line   │────▶│   agent.py   │────▶│   LLM API       │
│  (question)     │     │  (CLI tool)  │     │  (Qwen Code)    │
└─────────────────┘     └──────────────┘     └─────────────────┘
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
3. Sends the question to the LLM via HTTP POST
4. Returns a structured JSON response

**Input:**
```bash
uv run agent.py "What does REST stand for?"
```

**Output:**
```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

### Configuration (`.env.agent.secret`)

The agent reads the following environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for authentication | `sk-...` |
| `LLM_API_BASE` | Base URL of the LLM API | `http://vm-ip:port/v1` |
| `LLM_MODEL` | Model name to use | `qwen3-coder-plus` |

## LLM Provider

**Provider:** Qwen Code API

**Model:** `qwen3-coder-plus`

**Why Qwen Code:**
- 1000 free requests per day
- Available in Russia without restrictions
- No credit card required
- OpenAI-compatible API (easy integration)
- Strong tool-calling capabilities for future tasks

## Data Flow

1. **Input Parsing:** The question is read from `sys.argv[1]`
2. **Configuration Loading:** `.env.agent.secret` is parsed for API credentials
3. **API Request:** HTTP POST to `{LLM_API_BASE}/chat/completions` with:
   - Authorization header with Bearer token
   - JSON body with `model`, `messages`, and `temperature`
4. **Response Parsing:** Extract `choices[0].message.content` from the API response
5. **Output Formatting:** Return JSON with `answer` and `tool_calls` fields

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing `.env.agent.secret` | Exit with error to stderr, code 1 |
| Missing config variables | Exit with error to stderr, code 1 |
| Network error | Exit with error to stderr, code 1 |
| API timeout (>60s) | Exit with error to stderr, code 1 |
| Invalid API response | Exit with error to stderr, code 1 |
| Missing question argument | Print usage to stderr, exit code 1 |

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
uv run agent.py "What is the capital of France?"
```

### Expected Output

```json
{"answer": "The capital of France is Paris.", "tool_calls": []}
```

## Testing

Run the regression test:

```bash
uv run pytest backend/tests/unit/test_agent.py -v
```

## Future Extensions

In upcoming tasks, the agent will be extended with:
- **Tools:** Functions the agent can call (e.g., `read_file`, `query_api`)
- **Agentic Loop:** Multi-turn reasoning with tool selection
- **Domain Knowledge:** Integration with the LMS backend

## Files

| File | Description |
|------|-------------|
| `agent.py` | Main CLI entry point |
| `.env.agent.secret` | LLM configuration (gitignored) |
| `plans/task-1.md` | Implementation plan |
| `AGENT.md` | This documentation |
