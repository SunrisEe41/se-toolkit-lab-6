#!/usr/bin/env python3
"""
AI Agent CLI - Task 3: The System Agent

Usage:
    uv run agent.py "Your question here"

Output:
    JSON line to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    All debug output goes to stderr.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import dotenv

# Maximum tool calls per question
MAX_TOOL_CALLS = 15

# Project root directory (where agent.py is located)
PROJECT_ROOT = Path(__file__).parent.resolve()

# Tool definitions for OpenAI function-calling
TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file from the project repository. Use this to find specific information in wiki files or source code.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from project root (e.g., 'wiki/git-workflow.md', 'backend/main.py')",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and directories at a given path. Use this to discover available files in a directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative directory path from project root (e.g., 'wiki', 'backend')",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "query_api",
        "description": "Call the deployed backend API. Use this to query data from the database, check API endpoints, test HTTP responses, or get live system state. IMPORTANT: Always use the 'path' parameter for the API endpoint (not 'endpoint').",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, PUT, DELETE, etc.)",
                },
                "path": {
                    "type": "string",
                    "description": "API endpoint path starting with / (e.g., '/items/', '/analytics/completion-rate'). IMPORTANT: Always use 'path' for the endpoint, not 'endpoint'.",
                },
                "body": {
                    "type": "string",
                    "description": "Optional JSON request body for POST/PUT requests",
                },
                "auth": {
                    "type": "boolean",
                    "description": "Whether to include authentication header. Default true. Set to false to test unauthenticated endpoints.",
                },
            },
            "required": ["method", "path"],
        },
    },
]

# System prompt for the system agent
SYSTEM_PROMPT = """You are a documentation and system assistant that answers questions about software engineering topics using:
1. The project wiki (via list_files and read_file tools)
2. The deployed backend API (via query_api tool)
3. The project source code (via read_file tool)

Project structure:
- Wiki files are in the 'wiki/' directory (e.g., wiki/git.md, wiki/docker.md)
- Backend code is in the 'backend/' directory (e.g., backend/app/main.py, backend/app/routers/)
- Configuration files are at the root (e.g., docker-compose.yml, pyproject.toml)

You have access to three tools:
- list_files: List files in a directory. Use this first to discover what files are available.
- read_file: Read the contents of a file. Use this to find specific information in wiki files or source code.
- query_api: Call the backend API. Use this to query data or test API endpoints.

Tool selection guidelines:
- Use list_files to discover available files in a directory
- Use read_file to read wiki documentation or source code
- Use query_api to query the backend for data or test API endpoints

When to use query_api:
- Questions about data in the database (e.g., "How many items...?", "What is the completion rate...?")
- Questions about API behavior (e.g., "What status code...?", "What does the API return...?")
- Questions that require querying live system state
- Questions about HTTP responses or errors from endpoints

When to use read_file:
- Questions about documentation (e.g., "According to the wiki...", "What does the wiki say...?")
- Questions about source code (e.g., "What framework does...", "Read the source code to find...")
- Questions about configuration (e.g., "What ports are configured...", "Read docker-compose.yml...")

When to use list_files:
- Questions about what files exist (e.g., "What files are in the wiki?", "List all API router modules...")
- First step to discover available files before reading
- For backend routers: ALWAYS use list_files with path "backend/app/routers" to find all router files

CRITICAL RULES FOR COMPLETE ANSWERS:
- When asked to "list all", "find all", or "what are all" - you MUST examine EVERY relevant file
- When asked about router modules - list_files on "backend/app/routers", then read EACH .py file
- When asked about wiki files - list_files on "wiki", then read relevant files
- Do NOT stop after reading just one file when the question asks about multiple items
- Continue reading files until you have examined ALL of them
- Only provide your final answer after you have gathered information from ALL relevant files
- If you see 5 router files, you must read all 5 before answering
- IMPORTANT: Do NOT start your answer with "Let me" or "First" - these indicate you are not done
- IMPORTANT: Your response should ONLY contain tool calls until you have read ALL files
- IMPORTANT: Only when you have read ALL relevant files, provide the complete final answer
- NEVER give a partial answer - the user wants complete information about ALL items
- AFTER reading all files, you MUST provide a text answer summarizing what you found

Guidelines:
1. Choose the right tool for the question type
2. For wiki questions: use list_files with path "wiki" first, then read_file
3. For backend source questions: use list_files with path "backend" or read_file with "backend/..." paths
4. For API questions: use query_api directly with method and path
5. For questions about unauthenticated access (e.g., "without auth", "without header"): use query_api with auth=false
6. When you have enough information, provide a concise answer
7. Include the source as "wiki/filename.md#section-anchor" for wiki answers
8. For API queries, mention the endpoint used
9. Section anchors are lowercase with hyphens (e.g., #resolving-merge-conflicts)

Important:
- Make at most 15 tool calls total
- For "list all" questions, use your tool calls efficiently to read ALL relevant files
- If you cannot find the answer after reading relevant files or querying APIs, say so
- Keep answers concise and accurate
- For API errors, report the status code and error message
- NEVER give a partial answer when asked about "all" items - always check everything first
"""


def load_config() -> dict:
    """
    Load configuration from environment files.

    LLM config from .env.agent.secret
    LMS API key from .env.docker.secret
    AGENT_API_BASE_URL defaults to http://localhost:42002
    """
    # Load LLM config from .env.agent.secret
    env_agent_path = Path(__file__).parent / ".env.agent.secret"
    dotenv.load_dotenv(env_agent_path)

    # Load LMS config from .env.docker.secret
    env_docker_path = Path(__file__).parent / ".env.docker.secret"
    dotenv.load_dotenv(env_docker_path, override=True)

    config = {
        "llm_api_key": os.getenv("LLM_API_KEY"),
        "llm_api_base": os.getenv("LLM_API_BASE"),
        "llm_model": os.getenv("LLM_MODEL"),
        "lms_api_key": os.getenv("LMS_API_KEY"),
        "agent_api_base_url": os.getenv("AGENT_API_BASE_URL", "http://localhost:42002"),
    }

    # Validate required LLM config
    missing_llm = [
        key
        for key in ["llm_api_key", "llm_api_base", "llm_model"]
        if not config.get(key)
    ]
    if missing_llm:
        raise ValueError(
            f"Missing required LLM environment variables: {', '.join(missing_llm)}"
        )

    # LMS_API_KEY is required for query_api tool
    if not config.get("lms_api_key"):
        raise ValueError(
            "Missing required LMS_API_KEY environment variable for query_api tool"
        )

    return config


def validate_path(relative_path: str) -> Path:
    """
    Validate that a path is within the project directory.

    Returns the absolute path if valid, raises ValueError if path traversal detected.
    """
    # Reject paths with .. segments
    if ".." in relative_path.split(os.sep):
        raise ValueError(f"Path traversal detected: {relative_path}")

    # Resolve to absolute path
    requested_path = (PROJECT_ROOT / relative_path).resolve()

    # Check that resolved path is within project root
    if not str(requested_path).startswith(str(PROJECT_ROOT)):
        raise ValueError(f"Path traversal detected: {relative_path}")

    return requested_path


def read_file(path: str) -> str:
    """
    Read a file from the project repository.

    Args:
        path: Relative path from project root

    Returns:
        File contents as string, or error message
    """
    try:
        absolute_path = validate_path(path)

        if not absolute_path.exists():
            return f"File not found: {path}"

        if not absolute_path.is_file():
            return f"Not a file: {path}"

        content = absolute_path.read_text(encoding="utf-8")
        print(f"read_file: Read {path} ({len(content)} chars)", file=sys.stderr)
        return content

    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """
    List files and directories at a given path.

    Args:
        path: Relative directory path from project root

    Returns:
        Newline-separated listing of entries, or error message
    """
    try:
        absolute_path = validate_path(path)

        if not absolute_path.exists():
            return f"Directory not found: {path}"

        if not absolute_path.is_dir():
            return f"Not a directory: {path}"

        entries = sorted([entry.name for entry in absolute_path.iterdir()])
        result = "\n".join(entries)
        print(f"list_files: Listed {path} ({len(entries)} entries)", file=sys.stderr)
        return result

    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error listing directory: {e}"


def query_api(
    method: str,
    path: str,
    body: str = None,
    auth: bool = True,
    api_base_url: str = None,
    lms_api_key: str = None,
) -> str:
    """
    Call the backend API with optional authentication.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., '/items/')
        body: Optional JSON request body
        auth: Whether to include authentication header (default True)
        api_base_url: Base URL of the API
        lms_api_key: API key for authentication

    Returns:
        JSON string with status_code and body
    """
    url = f"{api_base_url}{path}"

    print(f"query_api: {method} {url} (auth={auth})", file=sys.stderr)

    # Build curl command with -L to follow redirects
    curl_cmd = [
        "curl",
        "-X",
        method,
        "-L",  # Follow redirects
        url,
        "-s",  # Silent mode
        "-w",
        "\n%{http_code}",  # Append status code
        "--no-keepalive",  # Disable connection reuse
    ]

    # Add auth header only if auth=True
    if auth:
        curl_cmd.extend(
            [
                "-H",
                f"Authorization: Bearer {lms_api_key}",
            ]
        )
    else:
        # Explicitly disable auth by not sending any auth header
        pass  # No auth headers added

    curl_cmd.extend(
        [
            "-H",
            "Content-Type: application/json",
        ]
    )

    if body:
        curl_cmd.extend(["-d", body])

    result = subprocess.run(
        curl_cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        return json.dumps({"status_code": 0, "body": f"curl error: {result.stderr}"})

    # Parse response - last line is status code
    lines = result.stdout.strip().split("\n")
    status_code = int(lines[-1]) if lines else 0
    body_content = "\n".join(lines[:-1]) if len(lines) > 1 else ""

    response_data = {"status_code": status_code, "body": body_content}

    print(f"query_api: Response status={status_code}", file=sys.stderr)

    return json.dumps(response_data)


def execute_tool(tool_name: str, args: dict, config: dict = None) -> str:
    """
    Execute a tool and return its result.

    Args:
        tool_name: Name of the tool to execute
        args: Arguments for the tool
        config: Configuration dict with API keys and URLs

    Returns:
        Tool result as string
    """
    if tool_name == "read_file":
        return read_file(args.get("path", ""))
    elif tool_name == "list_files":
        return list_files(args.get("path", ""))
    elif tool_name == "query_api":
        if config is None:
            return "Error: config not provided for query_api"
        # Handle both "path" and "endpoint" arguments (LLM may use either)
        path = args.get("path") or args.get("endpoint", "")
        # Handle auth parameter - convert string "False"/"True" to boolean
        auth_raw = args.get("auth", True)
        if isinstance(auth_raw, str):
            auth = auth_raw.lower() != "false"
        else:
            auth = bool(auth_raw) if auth_raw is not None else True
        return query_api(
            method=args.get("method", "GET"),
            path=path,
            body=args.get("body"),
            auth=auth,
            api_base_url=config.get("agent_api_base_url"),
            lms_api_key=config.get("lms_api_key"),
        )
    else:
        return f"Unknown tool: {tool_name}"


def extract_source(answer: str, tool_call_history: list) -> str:
    """
    Extract source from the answer or fall back to last read file.

    Args:
        answer: The LLM's answer text
        tool_call_history: List of tool calls made

    Returns:
        Source string (file path with section anchor), or empty string
    """
    # Try to find source pattern in answer (e.g., wiki/file.md#section)
    source_pattern = r"(wiki/[\w\-/]+\.md#[\w\-]+)"
    match = re.search(source_pattern, answer)
    if match:
        return match.group(1)

    # Try to find just file path pattern
    file_pattern = r"(wiki/[\w\-/]+\.md|backend/[\w\-/]+\.py|[\w\-/]+\.yml)"
    match = re.search(file_pattern, answer)
    if match:
        return match.group(1)

    # Fallback: use the last read_file path
    for call in reversed(tool_call_history):
        if call["tool"] == "read_file":
            path = call["args"].get("path", "")
            if path:
                # Try to extract section from answer
                section_match = re.search(r"##?\s+([A-Za-z0-9\s\-]+)", answer)
                if section_match:
                    section = section_match.group(1).lower().strip().replace(" ", "-")
                    return f"{path}#{section}"
                return path

    # For API queries or no source found, return empty string
    return ""


def call_llm(
    api_base: str, api_key: str, model: str, messages: list, tools: list = None
) -> dict:
    """
    Call the LLM API using curl.

    Args:
        api_base: Base URL of the API
        api_key: API key for authentication
        model: Model name to use
        messages: List of message dicts
        tools: Optional list of tool definitions

    Returns:
        Response data as dict
    """
    url = f"{api_base}/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    print(f"Calling LLM API: {url}", file=sys.stderr)

    # Use curl for the request (works reliably with the proxy)
    curl_cmd = [
        "curl",
        "-X",
        "POST",
        url,
        "-H",
        "Content-Type: application/json",
        "-H",
        f"Authorization: Bearer {api_key}",
        "-d",
        json.dumps(payload),
    ]

    result = subprocess.run(
        curl_cmd,
        capture_output=True,
        text=True,
        timeout=60,
    )

    print(f"curl exit code: {result.returncode}", file=sys.stderr)

    if result.returncode != 0:
        raise Exception(f"curl failed: {result.stderr}")

    response_data = json.loads(result.stdout)

    return response_data


def run_agentic_loop(config: dict, question: str) -> dict:
    """
    Run the agentic loop: send question to LLM, execute tool calls, feed results back.

    Args:
        config: Configuration dict with API keys and URLs
        question: User's question

    Returns:
        Output dict with answer, source, and tool_calls
    """
    # Initialize message history
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_call_history = []

    print("Starting agentic loop", file=sys.stderr)

    while len(tool_call_history) < MAX_TOOL_CALLS:
        # Call LLM with current message history
        print(f"LLM call (iteration {len(tool_call_history) + 1})", file=sys.stderr)

        response_data = call_llm(
            config["llm_api_base"],
            config["llm_api_key"],
            config["llm_model"],
            messages,
            TOOLS,
        )

        # Parse response
        choice = response_data["choices"][0]
        assistant_message = choice["message"]

        # Check if LLM made tool calls
        tool_calls = assistant_message.get("tool_calls", [])

        if tool_calls:
            # Add assistant message with tool calls to history
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.get("content"),
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["function"]["name"],
                                "arguments": tc["function"]["arguments"],
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            # Execute each tool call
            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])

                print(
                    f"Executing tool: {tool_name} with args: {tool_args}",
                    file=sys.stderr,
                )

                result = execute_tool(tool_name, tool_args, config)

                # Record in history
                tool_call_history.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "result": result,
                    }
                )

                # Add tool result to message history
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result,
                    }
                )

            # Continue loop - LLM will decide next action
            continue
        else:
            # No tool calls - LLM provided final answer
            final_answer = assistant_message.get("content") or ""
            print(
                f"LLM provided final answer (length={len(final_answer)})",
                file=sys.stderr,
            )

            # If answer is empty but we have tool calls, the LLM might not be done
            # In this case, prompt it to provide the answer
            if not final_answer.strip() and tool_call_history:
                print(
                    "Empty answer detected, prompting LLM to provide final answer...",
                    file=sys.stderr,
                )
                messages.append(
                    {
                        "role": "user",
                        "content": "Please provide your final answer based on the information you have gathered. Summarize all findings.",
                    }
                )
                continue

            # Extract source
            source = extract_source(final_answer, tool_call_history)
            print(f"Extracted source: {source}", file=sys.stderr)

            # Build output
            output = {
                "answer": final_answer.strip(),
                "source": source,
                "tool_calls": tool_call_history,
            }

            return output

    # Max tool calls reached
    print("Max tool calls reached, using best available answer", file=sys.stderr)

    # Get whatever answer we have from the last response
    final_answer = (
        assistant_message.get("content")
        or "Unable to complete the request within the tool call limit."
    )
    source = extract_source(final_answer, tool_call_history)

    output = {
        "answer": final_answer.strip(),
        "source": source,
        "tool_calls": tool_call_history,
    }

    return output


def main() -> int:
    """Main entry point."""
    # Parse command-line argument
    if len(sys.argv) < 2:
        print("Error: No question provided", file=sys.stderr)
        print('Usage: uv run agent.py "Your question here"', file=sys.stderr)
        return 1

    question = sys.argv[1]
    print(f"Received question: {question}", file=sys.stderr)

    # Load configuration
    try:
        config = load_config()
        print(
            f"Loaded config: model={config['llm_model']}, api_base={config['llm_api_base']}",
            file=sys.stderr,
        )
        print(f"API base URL: {config['agent_api_base_url']}", file=sys.stderr)
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Run agentic loop and get output
    try:
        output = run_agentic_loop(config, question)
    except Exception as e:
        print(f"Agentic loop error: {e}", file=sys.stderr)
        return 1

    # Output JSON
    print(json.dumps(output))

    return 0


if __name__ == "__main__":
    sys.exit(main())
