#!/usr/bin/env python3
"""CLI agent that connects to an LLM and answers questions using tools.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    All debug output goes to stderr.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx

# Maximum number of tool calls per question
MAX_TOOL_CALLS = 20

# Project root directory (where agent.py is located)
PROJECT_ROOT = Path(__file__).parent.resolve()


def load_env_file(filepath: str) -> dict[str, str]:
    """Load environment variables from a file."""
    env_file = Path(filepath)
    if not env_file.exists():
        return {}

    env_vars: dict[str, str] = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            env_vars[key] = value

    return env_vars


def load_env() -> dict[str, str]:
    """Load environment variables from .env.agent.secret."""
    env_vars = load_env_file(".env.agent.secret")
    
    if not env_vars:
        print("Error: .env.agent.secret not found", file=sys.stderr)
        print(
            "Copy .env.agent.example to .env.agent.secret and fill in your credentials",
            file=sys.stderr,
        )
        sys.exit(1)

    return env_vars


def load_docker_env() -> dict[str, str]:
    """Load environment variables from .env.docker.secret."""
    return load_env_file(".env.docker.secret")


def get_llm_config(env_vars: dict[str, str]) -> tuple[str, str, str]:
    """Extract LLM configuration from environment variables."""
    api_key = env_vars.get("LLM_API_KEY")
    api_base = env_vars.get("LLM_API_BASE")
    model = env_vars.get("LLM_MODEL")

    if not api_key:
        print("Error: LLM_API_KEY not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not api_base:
        print("Error: LLM_API_BASE not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not model:
        print("Error: LLM_MODEL not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    return api_key, api_base, model


def get_api_config(docker_env: dict[str, str]) -> tuple[str, str]:
    """Extract API configuration for query_api tool.
    
    Returns (lms_api_key, agent_api_base_url).
    """
    lms_api_key = docker_env.get("LMS_API_KEY")
    
    # AGENT_API_BASE_URL can come from:
    # 1. Environment variable (for autochecker) - highest priority
    # 2. .env.docker.secret
    # 3. Default: http://localhost:42001 (backend port)
    agent_api_base = os.environ.get(
        "AGENT_API_BASE_URL",
        docker_env.get("AGENT_API_BASE_URL", "http://localhost:42001")
    )

    if not lms_api_key:
        print("Error: LMS_API_KEY not set in .env.docker.secret", file=sys.stderr)
        sys.exit(1)

    return lms_api_key, agent_api_base


def validate_path(path: str) -> Path:
    """Validate and resolve a relative path against project root.

    Security: Rejects absolute paths, directory traversal (..), and paths
    outside the project root.
    """
    # Reject absolute paths
    if os.path.isabs(path):
        raise ValueError("Absolute paths not allowed")

    # Reject directory traversal
    if ".." in path:
        raise ValueError("Directory traversal not allowed")

    # Resolve against project root
    full_path = (PROJECT_ROOT / path).resolve()

    # Ensure path is within project root
    if not str(full_path).startswith(str(PROJECT_ROOT)):
        raise ValueError("Path outside project root")

    return full_path


def tool_read_file(path: str) -> str:
    """Read a file from the project repository.

    Args:
        path: Relative path from project root (e.g., 'wiki/git-workflow.md')

    Returns:
        File contents as a string, or an error message.
    """
    try:
        full_path = validate_path(path)

        if not full_path.exists():
            return f"Error: File not found: {path}"

        if not full_path.is_file():
            return f"Error: Not a file: {path}"

        return full_path.read_text()

    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


def tool_list_files(path: str) -> str:
    """List files and directories at a given path.

    Args:
        path: Relative directory path from project root (e.g., 'wiki')

    Returns:
        Newline-separated listing of entries, or an error message.
    """
    try:
        full_path = validate_path(path)

        if not full_path.exists():
            return f"Error: Directory not found: {path}"

        if not full_path.is_dir():
            return f"Error: Not a directory: {path}"

        entries = sorted([e.name for e in full_path.iterdir()])
        return "\n".join(entries)

    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error listing directory: {e}"


def tool_query_api(method: str, path: str, body: str = None, auth: bool = True,
                   lms_api_key: str = None, api_base_url: str = None) -> str:
    """Call the backend API and return the response.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        path: API path (e.g., '/items/', '/analytics/scores')
        body: JSON request body (optional, for POST/PUT)
        auth: Whether to include authentication header (default: True)
        lms_api_key: API key for authentication (from env)
        api_base_url: Base URL of the API (from env)

    Returns:
        JSON string with status_code and body, or error message.
    """
    # Use provided values or defaults
    if lms_api_key is None:
        docker_env = load_docker_env()
        lms_api_key = docker_env.get("LMS_API_KEY", "")
    
    if api_base_url is None:
        docker_env = load_docker_env()
        api_base_url = os.environ.get(
            "AGENT_API_BASE_URL",
            docker_env.get("AGENT_API_BASE_URL", "http://localhost:42001")
        )

    if not lms_api_key:
        return "Error: LMS_API_KEY not configured"

    # Build URL
    base = api_base_url.rstrip("/")
    path = path.lstrip("/")
    url = f"{base}/{path}"

    # Build headers
    headers = {
        "Content-Type": "application/json",
    }
    
    # Only add auth header if auth=True
    if auth and lms_api_key:
        headers["Authorization"] = f"Bearer {lms_api_key}"

    print(f"Calling API: {method} {url} (auth={auth})", file=sys.stderr)

    try:
        # Make the request
        if method.upper() == "GET":
            response = httpx.get(url, headers=headers, timeout=30)
        elif method.upper() == "POST":
            data = json.loads(body) if body else {}
            response = httpx.post(url, headers=headers, json=data, timeout=30)
        elif method.upper() == "PUT":
            data = json.loads(body) if body else {}
            response = httpx.put(url, headers=headers, json=data, timeout=30)
        elif method.upper() == "DELETE":
            response = httpx.delete(url, headers=headers, timeout=30)
        else:
            return json.dumps({"error": f"Unsupported method '{method}'", "status_code": None})

        # Build response
        result = {
            "status_code": response.status_code,
            "body": response.text,
        }

        try:
            result["body"] = response.json()
        except json.JSONDecodeError:
            result["body"] = response.text

        return json.dumps(result)

    except httpx.TimeoutException:
        return json.dumps({"error": "Request timed out", "status_code": None})
    except httpx.RequestError as e:
        return json.dumps({"error": str(e), "status_code": None})
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON in body: {e}", "status_code": None})
    except Exception as e:
        return json.dumps({"error": str(e), "status_code": None})


# Map tool names to functions
# Note: query_api needs special handling for env vars
TOOLS_MAP = {
    "read_file": tool_read_file,
    "list_files": tool_list_files,
    "query_api": tool_query_api,
}


def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Execute a tool and return the result.

    Args:
        tool_name: Name of the tool to execute
        args: Arguments to pass to the tool

    Returns:
        Tool result as a string
    """
    if tool_name not in TOOLS_MAP:
        return f"Error: Unknown tool '{tool_name}'"

    func = TOOLS_MAP[tool_name]

    # Validate required arguments
    import inspect
    sig = inspect.signature(func)
    required_params = [
        name for name, param in sig.parameters.items()
        if param.default == inspect.Parameter.empty
    ]

    for param in required_params:
        if param not in args or args[param] is None:
            return f"Error: Missing required argument '{param}' for tool '{tool_name}'"

    return func(**args)


def call_llm(
    messages: list[dict[str, str]],
    api_key: str,
    api_base: str,
    model: str,
    timeout: int = 120
) -> str:
    """Call the LLM API and return the response text.

    This version does NOT use tool calling - it relies on JSON parsing
    of the response text to detect tool calls.
    """
    url = f"{api_base}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
    }

    print(f"Calling LLM API at {url}...", file=sys.stderr)

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
    except httpx.TimeoutException:
        print(f"Error: LLM API request timed out after {timeout} seconds", file=sys.stderr)
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"Error: Failed to connect to LLM API: {e}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"Error: LLM API returned error status: {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text[:200]}", file=sys.stderr)
        sys.exit(1)

    try:
        data = response.json()
    except json.JSONDecodeError:
        print("Error: Invalid JSON response from LLM API", file=sys.stderr)
        sys.exit(1)

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        print(f"Error: Unexpected response format from LLM API: {e}", file=sys.stderr)
        print(f"Response: {data}", file=sys.stderr)
        sys.exit(1)

    return content


def parse_llm_response(content: str) -> dict[str, Any]:
    """Parse the LLM response to detect tool calls or final answer.

    The LLM is instructed to respond with JSON:
    - For tool calls: {"tool": "name", "args": {...}}
    - For final answer: {"answer": "...", "source": "..."}

    Returns dict with keys: tool, args, answer, source (as applicable)
    """
    content = content.strip()

    # Try to find JSON in the response - look for complete JSON objects
    # First try to parse the entire content as JSON
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON object pattern
    # Look for tool call pattern first
    tool_pattern = r'\{"tool":\s*"([^"]+)",\s*"args":\s*(\{[^}]*\})\}'
    tool_match = re.search(tool_pattern, content, re.DOTALL)
    if tool_match:
        try:
            tool_name = tool_match.group(1)
            args = json.loads(tool_match.group(2))
            return {"tool": tool_name, "args": args}
        except (json.JSONDecodeError, IndexError):
            pass

    # Look for answer pattern
    answer_pattern = r'\{"answer":\s*"([^"]*)",?\s*"source":\s*"([^"]*)"\}'
    answer_match = re.search(answer_pattern, content, re.DOTALL)
    if answer_match:
        return {"answer": answer_match.group(1), "source": answer_match.group(2)}

    # Try to find any JSON object
    json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # No JSON found - treat as final answer
    return {"answer": content, "source": ""}


def run_agentic_loop(
    question: str,
    api_key: str,
    api_base: str,
    model: str,
    lms_api_key: str,
    api_base_url: str,
    timeout: int = 120
) -> tuple[str, str, list[dict[str, Any]]]:
    """Run the agentic loop with tool calling via JSON parsing.

    Args:
        question: The user's question
        api_key: LLM API key for authentication
        api_base: LLM API base URL
        model: LLM model name to use
        lms_api_key: Backend API key for query_api
        api_base_url: Backend API base URL
        timeout: Request timeout in seconds

    Returns:
        Tuple of (answer, source, tool_calls)
    """
    # System prompt that instructs the LLM to use JSON for tool calls
    system_prompt = """You are a documentation and system assistant with access to three tools.

You have three tools:
1. list_files - List files in a directory (use to discover wiki files or source code)
   Args: {"path": "directory/path"}
   Example: {"tool": "list_files", "args": {"path": "wiki"}}

2. read_file - Read the contents of a file (wiki docs, source code, config files)
   Args: {"path": "relative/path/to/file"}
   Example: {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}}

3. query_api - Call the running backend API (for data queries, status codes, errors)
   Args: {"method": "GET|POST|PUT|DELETE", "path": "/api/endpoint", "body": "json_string", "auth": true|false}
   Example: {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}}
   Example: {"tool": "query_api", "args": {"method": "GET", "path": "/items/", "auth": false}}
   Note: method and path are required. body and auth are optional. auth defaults to true.
   Use auth=false to test unauthenticated access (e.g., check 401/403 responses).

To answer questions:
- For wiki/documentation questions: use list_files to discover wiki files, then read_file
- For source code questions: use list_files on backend/app/routers, then read_file on specific files
- For data queries (item count, scores): use query_api with GET
- For HTTP status codes: use query_api with auth=false to see 401/403
- For API error diagnosis: use query_api to see the error, then read_file to find the bug

Common paths:
- wiki/ - Project documentation
- backend/app/routers/ - API router modules (items.py, analytics.py, etc.)
- backend/app/ - Main application code
- backend/app/etl.py - ETL pipeline code
- docker-compose.yml - Docker configuration

IMPORTANT: Always respond with valid JSON.

To call a tool, respond with:
{"tool": "tool_name", "args": {"param": "value"}}

For the final answer, respond with:
{"answer": "your answer", "source": "wiki/file.md#section"}

The source is optional for system questions. For wiki questions, include the section anchor."""

    # Initialize conversation
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    tool_calls_log: list[dict[str, Any]] = []
    tool_call_count = 0
    conversation_history: list[str] = []

    while tool_call_count < MAX_TOOL_CALLS:
        # Build conversation context
        context_messages = messages.copy()

        # Add conversation history (tool results)
        for entry in conversation_history:
            context_messages.append({"role": "user", "content": entry})

        # Call LLM
        response_text = call_llm(context_messages, api_key, api_base, model, timeout)
        print(f"LLM response: {response_text[:200]}...", file=sys.stderr)

        # Parse response
        parsed = parse_llm_response(response_text)

        # Check if this is a tool call
        if "tool" in parsed and "args" in parsed:
            tool_name = parsed["tool"]
            args = parsed["args"]

            print(f"Executing tool: {tool_name} with args: {args}", file=sys.stderr)

            # Execute the tool
            # For query_api, pass the API credentials
            if tool_name == "query_api":
                result = execute_query_api_with_auth(args, lms_api_key, api_base_url)
            else:
                result = execute_tool(tool_name, args)

            # Log the tool call
            tool_calls_log.append({
                "tool": tool_name,
                "args": args,
                "result": result,
            })

            # Add to conversation history
            conversation_history.append(f"Tool result for {tool_name}: {result}")

            tool_call_count += 1
            continue

        # Check if this is a final answer
        if "answer" in parsed:
            answer = parsed["answer"]
            source = parsed.get("source", "")
            return answer, source, tool_calls_log

        # If neither tool call nor answer, treat as final answer
        return response_text.strip(), "", tool_calls_log

    # Max tool calls reached
    print(f"Warning: Reached maximum tool calls ({MAX_TOOL_CALLS})", file=sys.stderr)

    # Make one final call to get the answer
    context_messages = messages.copy()
    for entry in conversation_history:
        context_messages.append({"role": "user", "content": entry})
    context_messages.append({
        "role": "user",
        "content": "You have reached the maximum number of tool calls. Provide your final answer based on the information gathered so far. Respond with JSON: {\"answer\": \"...\", \"source\": \"...\"}"
    })

    response_text = call_llm(context_messages, api_key, api_base, model, timeout)
    parsed = parse_llm_response(response_text)

    answer = parsed.get("answer", response_text.strip())
    source = parsed.get("source", "")

    return answer, source, tool_calls_log


def execute_query_api_with_auth(args: dict[str, Any], lms_api_key: str, api_base_url: str) -> str:
    """Execute query_api tool with proper authentication."""
    method = args.get("method", "GET")
    path = args.get("path", "")
    body = args.get("body")
    auth = args.get("auth", True)  # Default to True for backward compatibility
    
    return tool_query_api(method, path, body, auth, lms_api_key, api_base_url)


def extract_source_from_answer(answer: str, tool_calls_log: list[dict[str, Any]]) -> str:
    """Extract or generate a source reference from the answer.

    Looks for patterns like 'wiki/file.md#section' in the answer.
    If not found, uses the last read_file path.
    """
    # Look for wiki file reference pattern
    pattern = r"(wiki/[\w\-\.]+#[\w\-]+)"
    match = re.search(pattern, answer, re.IGNORECASE)

    if match:
        return match.group(1)

    # Fallback: use the last read_file path
    for call in reversed(tool_calls_log):
        if call["tool"] == "read_file":
            path = call["args"].get("path", "")
            if path.startswith("wiki/"):
                return path

    return ""


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LLM-powered documentation and system agent with tool calling"
    )
    parser.add_argument("question", help="The question to answer")
    args = parser.parse_args()

    # Load LLM configuration
    llm_env = load_env()
    api_key, api_base, model = get_llm_config(llm_env)

    # Load API configuration for query_api
    docker_env = load_docker_env()
    lms_api_key, api_base_url = get_api_config(docker_env)

    # Run agentic loop
    answer, source, tool_calls = run_agentic_loop(
        args.question, api_key, api_base, model, lms_api_key, api_base_url
    )

    # Output result as JSON
    result = {
        "answer": answer,
        "source": source,
        "tool_calls": tool_calls,
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
