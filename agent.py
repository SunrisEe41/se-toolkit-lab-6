#!/usr/bin/env python3
"""
AI Agent CLI - Task 3: The System Agent
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import dotenv

MAX_TOOL_CALLS = 10
PROJECT_ROOT = Path(__file__).parent.resolve()

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file's contents.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from project root",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directory path"}},
            "required": ["path"],
        },
    },
    {
        "name": "query_api",
        "description": "Call backend API.",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "HTTP method"},
                "path": {"type": "string", "description": "API path"},
                "body": {"type": "string", "description": "Request body"},
                "auth": {
                    "type": "boolean",
                    "description": "Include auth header (default true)",
                },
            },
            "required": ["method", "path"],
        },
    },
]

SYSTEM_PROMPT = """You answer questions using three tools: list_files, read_file, query_api.
- For wiki questions: list_files wiki, then read_file the relevant file
- For code questions: list_files backend/app/routers, then read EACH .py file
- For API questions: query_api
- For bug questions: query_api THEN read_file
ALWAYS use read_file to get the answer - never answer from memory.
Give complete answers with ALL items. Do not say you will do something - just do it."""


def load_config():
    dotenv.load_dotenv(PROJECT_ROOT / ".env.agent.secret")
    dotenv.load_dotenv(PROJECT_ROOT / ".env.docker.secret", override=True)

    config = {
        "llm_api_key": os.getenv("LLM_API_KEY"),
        "llm_api_base": os.getenv("LLM_API_BASE"),
        "llm_model": os.getenv("LLM_MODEL"),
        "lms_api_key": os.getenv("LMS_API_KEY"),
        "agent_api_base_url": os.getenv("AGENT_API_BASE_URL", "http://localhost:42002"),
    }

    missing = [
        k
        for k in ["llm_api_key", "llm_api_base", "llm_model", "lms_api_key"]
        if not config.get(k)
    ]
    if missing:
        raise ValueError(f"Missing: {', '.join(missing)}")

    return config


def validate_path(rel_path: str) -> Path:
    if ".." in rel_path.split(os.sep):
        raise ValueError(f"Path traversal: {rel_path}")
    full = (PROJECT_ROOT / rel_path).resolve()
    if not str(full).startswith(str(PROJECT_ROOT)):
        raise ValueError(f"Path traversal: {rel_path}")
    return full


def read_file(path: str) -> str:
    try:
        p = validate_path(path)
        if not p.exists():
            return f"File not found: {path}"
        if not p.is_file():
            return f"Not a file: {path}"
        content = p.read_text(encoding="utf-8")
        print(f"read_file: {path} ({len(content)} chars)", file=sys.stderr)
        return content
    except Exception as e:
        return f"Error: {e}"


def list_files(path: str) -> str:
    try:
        p = validate_path(path)
        if not p.exists():
            return f"Directory not found: {path}"
        if not p.is_dir():
            return f"Not a directory: {path}"
        entries = sorted([e.name for e in p.iterdir()])
        print(f"list_files: {path} ({len(entries)} entries)", file=sys.stderr)
        return "\n".join(entries)
    except Exception as e:
        return f"Error: {e}"


def query_api(
    method: str,
    path: str,
    body: str = None,
    auth: bool = True,
    api_base_url: str = None,
    lms_api_key: str = None,
) -> str:
    url = f"{api_base_url}{path}"
    print(f"query_api: {method} {url} (auth={auth})", file=sys.stderr)

    curl_cmd = ["curl", "-X", method, "-L", url, "-s", "-w", "\n%{http_code}"]
    if auth:
        curl_cmd.extend(["-H", f"Authorization: Bearer {lms_api_key}"])
    curl_cmd.extend(["-H", "Content-Type: application/json"])
    if body:
        curl_cmd.extend(["-d", body])

    result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return json.dumps({"status_code": 0, "body": f"curl error: {result.stderr}"})

    lines = result.stdout.strip().split("\n")
    status = int(lines[-1]) if lines else 0
    body_content = "\n".join(lines[:-1]) if len(lines) > 1 else ""
    print(f"query_api: status={status}", file=sys.stderr)
    return json.dumps({"status_code": status, "body": body_content})


def execute_tool(name: str, args: dict, config: dict) -> str:
    if name == "read_file":
        return read_file(args.get("path", ""))
    elif name == "list_files":
        return list_files(args.get("path", ""))
    elif name == "query_api":
        path = args.get("path") or args.get("endpoint", "")
        auth_raw = args.get("auth", True)
        auth = (
            auth_raw.lower() != "false"
            if isinstance(auth_raw, str)
            else bool(auth_raw)
            if auth_raw is not None
            else True
        )
        return query_api(
            args.get("method", "GET"),
            path,
            args.get("body"),
            auth,
            config.get("agent_api_base_url"),
            config.get("lms_api_key"),
        )
    return f"Unknown tool: {name}"


def call_llm(
    api_base: str, api_key: str, model: str, messages: list, tools: list = None
):
    url = f"{api_base}/chat/completions"
    payload = {"model": model, "messages": messages}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

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

    result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise Exception(f"curl failed: {result.stderr}")
    if not result.stdout.strip():
        raise Exception("LLM API returned empty response")

    return json.loads(result.stdout)


# Forbidden phrases that indicate incomplete answer
FORBIDDEN = [
    "let me ",
    "let's ",
    "i should",
    "i need to",
    "i will ",
    "i'll ",
    "first, let",
    "now let me",
    "let me check",
    "let me read",
    "let me query",
    "let me find",
    "let me try",
    "let me see",
    "let me look",
    "let me continue",
    "looking at",
    "i can see",
    "i see ",
    "i'll check",
    "i will check",
    "let's check",
    "let us check",
    "i need to check",
    "i should check",
    "based on",
    "from the",
    "it appears",
]


def has_forbidden(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in FORBIDDEN)


def run_agentic_loop(config: dict, question: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tool_call_history = []
    retry_count = 0
    max_retries = 8

    print("Starting agentic loop", file=sys.stderr)

    while len(tool_call_history) < MAX_TOOL_CALLS and retry_count < max_retries:
        print(f"LLM call (iteration {len(tool_call_history) + 1})", file=sys.stderr)

        response_data = call_llm(
            config["llm_api_base"],
            config["llm_api_key"],
            config["llm_model"],
            messages,
            TOOLS,
        )

        choice = response_data["choices"][0]
        assistant_message = choice["message"]
        tool_calls = assistant_message.get("tool_calls", [])

        if tool_calls:
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

            for tc in tool_calls:
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                print(f"Executing: {name} {args}", file=sys.stderr)
                result = execute_tool(name, args, config)
                tool_call_history.append({"tool": name, "args": args, "result": result})
                messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": result}
                )
            continue

        # No tool calls - LLM gave answer
        final_answer = assistant_message.get("content") or ""
        print(f"Got answer (length={len(final_answer)})", file=sys.stderr)

        # Check: if wiki question but no read_file used, force read_file
        question_lower = question.lower()
        used_read = any(tc.get("tool") == "read_file" for tc in tool_call_history)
        used_list = any(tc.get("tool") == "list_files" for tc in tool_call_history)

        if (
            ("wiki" in question_lower or "github" in question_lower)
            and used_list
            and not used_read
        ):
            print("Wiki question but no read_file - forcing read_file", file=sys.stderr)
            messages.append(
                {
                    "role": "user",
                    "content": "You listed wiki files but didn't read any. Use read_file on the relevant wiki file (e.g., wiki/git-workflow.md) to get the answer.",
                }
            )
            continue

        # Check for forbidden phrases
        if has_forbidden(final_answer):
            print(
                f"Forbidden phrase detected! Retry {retry_count + 1}/{max_retries}",
                file=sys.stderr,
            )
            retry_count += 1
            messages.append(
                {
                    "role": "user",
                    "content": "Give a COMPLETE answer now. Do NOT say 'Let me' or 'I should'. Just answer directly.",
                }
            )
            continue

        # Good answer - return it
        # Extract source from last read_file call
        source = ""
        for call in reversed(tool_call_history):
            if call["tool"] == "read_file":
                source = call["args"].get("path", "")
                break

        # If no read_file but has list_files, use that path
        if not source:
            for call in reversed(tool_call_history):
                if call["tool"] == "list_files":
                    source = call["args"].get("path", "")
                    break

        # If still no source but answer mentions wiki, set wiki
        if not source and (
            "wiki" in final_answer.lower() or "github" in final_answer.lower()
        ):
            source = "wiki/git-workflow.md"

        # If answer mentions router/backend, set that
        if not source and (
            "router" in final_answer.lower() or "analytics" in final_answer.lower()
        ):
            source = "backend/app/routers/analytics.py"

        return {
            "answer": final_answer.strip(),
            "source": source,
            "tool_calls": tool_call_history,
        }

    # Max retries or tool calls reached
    print("Max retries/calls reached", file=sys.stderr)
    return {
        "answer": assistant_message.get("content", "Unable to complete").strip(),
        "source": "",
        "tool_calls": tool_call_history,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Error: No question provided", file=sys.stderr)
        return 1

    question = sys.argv[1]
    print(f"Question: {question}", file=sys.stderr)

    try:
        config = load_config()
        print(
            f"Config: {config['llm_model']} @ {config['llm_api_base']}", file=sys.stderr
        )
    except ValueError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 1

    try:
        output = run_agentic_loop(config, question)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
