#!/usr/bin/env python3
"""
AI Agent CLI - Task 2: The Documentation Agent

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
MAX_TOOL_CALLS = 10

# Project root directory (where agent.py is located)
PROJECT_ROOT = Path(__file__).parent.resolve()

# Tool definitions for OpenAI function-calling
TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file from the project repository. Use this to find specific information in wiki files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')",
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
                    "description": "Relative directory path from project root (e.g., 'wiki')",
                }
            },
            "required": ["path"],
        },
    },
]

# System prompt for the documentation agent
SYSTEM_PROMPT = """You are a documentation assistant that answers questions about software engineering topics using the project wiki.

You have access to two tools:
- list_files: List files in a directory. Use this first to discover what wiki files are available.
- read_file: Read the contents of a file. Use this to find specific information in wiki files.

Guidelines:
1. First use list_files to discover relevant wiki files (e.g., list_files with path "wiki")
2. Then use read_file to read specific files and find the answer
3. When you have enough information, provide a concise answer
4. Always include the source as "wiki/filename.md#section-anchor" where section-anchor is the relevant section
5. Section anchors are lowercase with hyphens (e.g., #resolving-merge-conflicts, #create-a-lab-task-issue)

Important:
- Make at most 10 tool calls total
- If you cannot find the answer after reading relevant files, say so
- Keep answers concise and accurate
- Always cite your source with the exact file path and section anchor
"""


def load_config() -> dict:
    """Load configuration from .env.agent.secret file."""
    env_path = Path(__file__).parent / ".env.agent.secret"
    dotenv.load_dotenv(env_path)

    config = {
        "api_key": os.getenv("LLM_API_KEY"),
        "api_base": os.getenv("LLM_API_BASE"),
        "model": os.getenv("LLM_MODEL"),
    }

    # Validate required config
    missing = [key for key, value in config.items() if not value]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}"
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


def execute_tool(tool_name: str, args: dict) -> str:
    """
    Execute a tool and return its result.

    Args:
        tool_name: Name of the tool to execute
        args: Arguments for the tool

    Returns:
        Tool result as string
    """
    if tool_name == "read_file":
        return read_file(args.get("path", ""))
    elif tool_name == "list_files":
        return list_files(args.get("path", ""))
    else:
        return f"Unknown tool: {tool_name}"


def extract_source(answer: str, tool_call_history: list) -> str:
    """
    Extract source from the answer or fall back to last read file.

    Args:
        answer: The LLM's answer text
        tool_call_history: List of tool calls made

    Returns:
        Source string (file path with section anchor)
    """
    # Try to find source pattern in answer (e.g., wiki/file.md#section)
    source_pattern = r"(wiki/[\w\-/]+\.md#[\w\-]+)"
    match = re.search(source_pattern, answer)
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

    # Last resort fallback
    return "wiki/unknown.md"


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


def run_agentic_loop(api_base: str, api_key: str, model: str, question: str) -> dict:
    """
    Run the agentic loop: send question to LLM, execute tool calls, feed results back.

    Args:
        api_base: Base URL of the API
        api_key: API key for authentication
        model: Model name to use
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

        response_data = call_llm(api_base, api_key, model, messages, TOOLS)

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

                result = execute_tool(tool_name, tool_args)

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
            final_answer = assistant_message.get("content", "")
            print(f"LLM provided final answer", file=sys.stderr)

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
            f"Loaded config: model={config['model']}, api_base={config['api_base']}",
            file=sys.stderr,
        )
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Run agentic loop and get output
    try:
        output = run_agentic_loop(
            config["api_base"],
            config["api_key"],
            config["model"],
            question,
        )
    except Exception as e:
        print(f"Agentic loop error: {e}", file=sys.stderr)
        return 1

    # Output JSON
    print(json.dumps(output))

    return 0


if __name__ == "__main__":
    sys.exit(main())
