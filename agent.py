#!/usr/bin/env python3
"""
Lab  assistant agent — answers questions using an LLM with tools.

Usage:
    uv run agent.py "What does REST stand for?"

Output:
    {
      "answer": "...",
      "source": "wiki/rest-api.md#what-is-rest",
      "tool_calls": [...]
    }
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

# Load LLM configuration from .env.agent.secret
load_dotenv(".env.agent.secret")

# LLM configuration
LLM_API_BASE = os.getenv("LLM_API_BASE")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")

# Backend API configuration (load from .env.docker.secret)
load_dotenv(".env.docker.secret", override=True)
LMS_API_KEY = os.getenv("LMS_API_KEY")
AGENT_API_BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002")

# Project root for tool path resolution
PROJECT_ROOT = Path(__file__).parent.resolve()

# Maximum tool calls per query
MAX_TOOL_CALLS = 10

# Tool definitions for LLM function calling
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read contents of a file from the project repository. Use this to read file contents after discovering relevant files with list_files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/rest-api.md')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path in the project repository. Use this to discover files in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki/')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Query the backend API to get real-time data or perform actions. Use this for questions about database contents, statistics, or system state. Do NOT use for static documentation questions — use read_file or list_files for those.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE, etc.)",
                    },
                    "path": {
                        "type": "string",
                        "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate')",
                    },
                    "body": {
                        "type": "string",
                        "description": "JSON request body for POST/PUT requests (optional)",
                    },
                    "auth": {
                        "type": "boolean",
                        "description": "Whether to include Authorization header (default: true). Set to false to test unauthenticated access.",
                    },
                },
                "required": ["method", "path"],
            },
        },
    },
]

# System prompt for the agent
SYSTEM_PROMPT = """You are a helpful assistant that answers questions using the project repository and backend API.

You have access to these tools:
- list_files(path): List files/directories at a given path
- read_file(path): Read contents of a file
- query_api(method, path, body, auth): Query the backend API for real-time data

Decision workflow:
1. For static documentation questions (e.g., "What is REST?", "How to protect a branch?") → use list_files and read_file in wiki/
2. For data-dependent questions (e.g., "How many items?", "What's the completion rate?") → use query_api
3. For system facts (e.g., "What framework?", "What port?") → use read_file on source code (backend/main.py, docker-compose.yml)
4. To test unauthenticated access (e.g., "What status code without auth?") → use query_api with auth=false
5. For bug diagnosis questions:
   - First, query the API to reproduce the error and get the traceback
   - Then, read the source code at the file/line mentioned in the traceback
   - Explain the root cause and suggest a fix

Rules:
- Always provide the source file path where you found the answer (for wiki/code questions)
- For API queries, include the endpoint path in your answer
- At the end of your answer, add a line: "Source: <file-path>" (e.g., "Source: backend/app/routers/analytics.py")
- For bug diagnosis, always cite the source file where the bug is located
- If you can't find the answer after exploring, say so honestly
- Don't make up information not present in the files or API responses
- When you find the answer, respond with the answer and source, do not make additional tool calls
"""


def is_safe_path(requested_path: str) -> bool:
    """Check if the requested path is within the project directory.

    Security: prevents path traversal attacks (e.g., ../../.env)
    """
    # Reject absolute paths
    if os.path.isabs(requested_path):
        return False

    # Reject paths with .. components
    if ".." in requested_path:
        return False

    # Resolve the full path
    full_path = (PROJECT_ROOT / requested_path).resolve()

    # Ensure it's within project root
    return str(full_path).startswith(str(PROJECT_ROOT))


def read_file(path: str) -> str:
    """Read contents of a file from the project repository.

    Args:
        path: Relative path from project root

    Returns:
        File contents as string, or error message
    """
    if not is_safe_path(path):
        return f"Error: Invalid path '{path}'. Path traversal not allowed."

    file_path = PROJECT_ROOT / path

    if not file_path.exists():
        return f"Error: File '{path}' does not exist."

    if not file_path.is_file():
        return f"Error: '{path}' is not a file."

    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """List files and directories at a given path.

    Args:
        path: Relative directory path from project root

    Returns:
        Newline-separated listing of entries, or error message
    """
    if not is_safe_path(path):
        return f"Error: Invalid path '{path}'. Path traversal not allowed."

    dir_path = PROJECT_ROOT / path

    if not dir_path.exists():
        return f"Error: Directory '{path}' does not exist."

    if not dir_path.is_dir():
        return f"Error: '{path}' is not a directory."

    try:
        entries = sorted(dir_path.iterdir())
        lines = [entry.name for entry in entries]
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing directory: {e}"


def query_api(
    method: str, path: str, body: str | None = None, auth: bool = True
) -> str:
    """Query the backend API with optional authentication.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        path: API endpoint path (e.g., '/items/', '/analytics/completion-rate')
        body: Optional JSON request body for POST/PUT requests
        auth: Whether to include Authorization header (default: true)

    Returns:
        JSON string with status_code and body, or error message
    """
    import json as json_module

    # Build the full URL
    base_url = AGENT_API_BASE_URL.rstrip("/")
    # Ensure path starts with /
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base_url}{path}"

    headers = {
        "Content-Type": "application/json",
    }

    # Add authorization header if requested
    if auth:
        if not LMS_API_KEY:
            return json_module.dumps(
                {
                    "status_code": 500,
                    "body": "Error: LMS_API_KEY not configured. Check .env.docker.secret.",
                }
            )
        headers["Authorization"] = f"Bearer {LMS_API_KEY}"

    try:
        with httpx.Client() as client:
            # Parse body if provided
            json_body = None
            if body:
                json_body = json_module.loads(body)

            # Make the request
            if method.upper() == "GET":
                response = client.get(url, headers=headers, timeout=30.0)
            elif method.upper() == "POST":
                response = client.post(
                    url, headers=headers, json=json_body, timeout=30.0
                )
            elif method.upper() == "PUT":
                response = client.put(
                    url, headers=headers, json=json_body, timeout=30.0
                )
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers, timeout=30.0)
            else:
                return json_module.dumps(
                    {
                        "status_code": 400,
                        "body": f"Error: Unsupported HTTP method '{method}'",
                    }
                )

            # Return response as JSON string
            return json_module.dumps(
                {"status_code": response.status_code, "body": response.text}
            )

    except httpx.ReadTimeout as e:
        return json_module.dumps(
            {"status_code": 504, "body": f"Error: Request timed out: {e}"}
        )
    except httpx.ConnectError as e:
        return json_module.dumps(
            {
                "status_code": 503,
                "body": f"Error: Cannot connect to backend API at {url}: {e}",
            }
        )
    except json_module.JSONDecodeError as e:
        return json_module.dumps(
            {"status_code": 400, "body": f"Error: Invalid JSON in body: {e}"}
        )
    except Exception as e:
        return json_module.dumps({"status_code": 500, "body": f"Error: {e}"})


# Map of tool names to functions
TOOLS = {
    "read_file": read_file,
    "list_files": list_files,
    "query_api": query_api,
}


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool by name with the given arguments.

    Args:
        name: Tool name (e.g., 'read_file')
        arguments: Tool arguments as dict

    Returns:
        Tool result as string
    """
    if name not in TOOLS:
        return f"Error: Unknown tool '{name}'"

    func = TOOLS[name]
    try:
        return func(**arguments)
    except TypeError as e:
        return f"Error: Invalid arguments for {name}: {e}"
    except Exception as e:
        return f"Error executing {name}: {e}"


def call_llm(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Send messages to the LLM and return the response.

    Args:
        messages: List of message dicts with 'role' and 'content'
        tools: Optional list of tool definitions

    Returns:
        LLM response as dict
    """
    if not LLM_API_BASE or not LLM_API_KEY:
        raise RuntimeError(
            "LLM not configured. Check .env.agent.secret and ensure "
            "LLM_API_BASE and LLM_API_KEY are set."
        )

    url = f"{LLM_API_BASE.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": LLM_MODEL or "qwen3-coder-plus",
        "messages": messages,
        "temperature": 0.7,
    }

    if tools:
        payload["tools"] = tools

    max_retries = 3
    retry_delay = 2.0

    with httpx.Client() as client:
        for attempt in range(max_retries):
            try:
                response = client.post(url, headers=headers, json=payload, timeout=60.0)

                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        raise RuntimeError("Max retries exceeded due to rate limiting")

                response.raise_for_status()
                return response.json()

            except httpx.ReadTimeout as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                raise RuntimeError("Request timed out after max retries") from e

    raise RuntimeError("LLM request failed after all retries")


def run_agentic_loop(question: str) -> dict[str, Any]:
    """Run the agentic loop to answer a question.

    Args:
        question: User's question

    Returns:
        Result dict with 'answer', 'source', and 'tool_calls'
    """
    # Initialize messages with system prompt and user question
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    # Track tool calls for output
    tool_calls_log: list[dict[str, Any]] = []

    # Agentic loop
    for iteration in range(MAX_TOOL_CALLS):
        # Call LLM with tool definitions
        response = call_llm(messages, tools=TOOL_DEFINITIONS)

        # Parse response
        try:
            choice = response["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Unexpected LLM response: {response}") from e

        # Check for tool calls
        tool_calls = choice.get("tool_calls")

        if tool_calls:
            # LLM wants to call tools

            # Add assistant message with tool calls
            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": tool_calls,
                }
            )

            # Execute each tool call
            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])
                tool_call_id = tool_call["id"]

                # Execute tool
                result = execute_tool(tool_name, tool_args)

                # Log tool call for output
                tool_calls_log.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "result": result,
                    }
                )

                # Add tool result as tool role message
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result,
                    }
                )

            # Loop back to call LLM with tool results
            continue

        else:
            # LLM returned content without tool calls - final answer
            # Note: Use (choice.get("content") or "") because LLM may return content: null
            answer = choice.get("content") or ""

            # Extract source from answer (look for source reference)
            source = ""
            if "source:" in answer.lower():
                # Try to extract source from the answer
                import re

                # Match patterns like:
                # - "Source: wiki/github.md"
                # - "Source: `backend/app/routers/analytics.py`"
                # - "Source: backend/app/routers/analytics.py, line 212"
                # Find all matches and prefer file paths over API endpoints
                matches = re.findall(
                    r"source:\s*`?([a-zA-Z0-9_/.-]+\.(py|md|json|yml|yaml))",
                    answer,
                    re.IGNORECASE,
                )
                if matches:
                    # Extract just the file paths (first group)
                    file_paths = [m[0] for m in matches]
                    # Prefer Python files
                    for path in file_paths:
                        if path.endswith(".py"):
                            source = path
                            break
                    if not source:
                        source = file_paths[0]

            return {
                "answer": answer,
                "source": source,
                "tool_calls": tool_calls_log,
            }

    # Max iterations reached
    return {
        "answer": "Unable to find answer within maximum tool calls.",
        "source": "",
        "tool_calls": tool_calls_log,
    }


def main():
    if len(sys.argv) != 2:
        print('Usage: uv run agent.py "<question>"', file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    try:
        result = run_agentic_loop(question)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Output single JSON line to stdout
    print(json.dumps(result))


if __name__ == "__main__":
    main()
