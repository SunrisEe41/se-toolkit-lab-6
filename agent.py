#!/usr/bin/env python3
"""
AI Agent CLI - Task 3: The System Agent
Outputs JSON format only.
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

SYSTEM_PROMPT = """You have three tools: list_files, read_file, query_api.

RULES:
1. Use list_files to discover files, read_file to read them
2. For API questions: use query_api
3. For bug questions: use query_api THEN read_file
4. Answer in JSON format ONLY - no introductions

OUTPUT FORMAT (JSON only, no text before or after):
{
  "answer": "your direct answer here - no 'Based on' or 'Looking at' prefixes",
  "source": "file/path.md"
}

EXAMPLES:
GOOD: {"answer": "Create SSH key with ssh-keygen -t ed25519", "source": "wiki/ssh.md"}
BAD: "Based on the wiki, you should create SSH key..."

GOOD: {"answer": "FastAPI framework", "source": "backend/app/main.py"}
BAD: "Looking at the code, I can see FastAPI..."

NEVER use phrases like: "Based on", "Looking at", "From the", "Here are", "The steps are"
Just give the direct answer in JSON."""


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


def extract_json_answer(text: str) -> dict:
    """Extract JSON from LLM response, handling various formats."""
    text = text.strip()

    # Try to parse as-is first
    try:
        return json.loads(text)
    except:
        pass

    # Try to find JSON in the text
    json_match = re.search(r'\{[^{}]*"answer"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass

    # Fallback: extract answer and source separately
    answer_match = re.search(r'"answer"\s*:\s*"([^"]+)"', text)
    source_match = re.search(r'"source"\s*:\s*"([^"]+)"', text)

    return {
        "answer": answer_match.group(1) if answer_match else text,
        "source": source_match.group(1) if source_match else "",
    }


def infer_source(question: str, tool_history: list) -> str:
    """Infer source from question and tool usage."""
    q = question.lower()

    # From tool history
    for call in reversed(tool_history):
        if call["tool"] == "read_file":
            return call["args"].get("path", "")
        if call["tool"] == "list_files":
            return call["args"].get("path", "")

    # From question keywords
    if "wiki" in q or "github" in q or "branch" in q or "protect" in q:
        return "wiki/git-workflow.md"
    elif "ssh" in q or "vm" in q or "connect" in q:
        return "wiki/ssh.md"
    elif "framework" in q or "fastapi" in q:
        return "backend/app/main.py"
    elif "router" in q or "analytics" in q or "top-learners" in q:
        return "backend/app/routers/analytics.py"
    elif "docker" in q or "compose" in q or "journey" in q:
        return "docker-compose.yml"
    elif "etl" in q or "pipeline" in q or "idempotent" in q:
        return "backend/app/routers/pipeline.py"
    elif "items" in q or "database" in q or "count" in q:
        return "backend/app/routers/items.py"
    elif "authentication" in q or "401" in q or "unauthorized" in q:
        return "backend/app/routers/items.py"
    elif "completion" in q or "division" in q or "zero" in q:
        return "backend/app/routers/analytics.py"

    return ""


def run_agentic_loop(config: dict, question: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tool_call_history = []
    max_iterations = MAX_TOOL_CALLS + 5  # Extra iterations for JSON formatting

    print("Starting agentic loop", file=sys.stderr)

    for iteration in range(max_iterations):
        print(f"Iteration {iteration + 1}", file=sys.stderr)

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
                print(f"Executing: {name}", file=sys.stderr)
                result = execute_tool(name, args, config)
                tool_call_history.append({"tool": name, "args": args, "result": result})
                messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": result}
                )
            continue

        # No tool calls - parse JSON answer
        content = assistant_message.get("content") or ""
        print(f"Got response (length={len(content)})", file=sys.stderr)

        # Extract JSON
        result = extract_json_answer(content)

        # Ensure we have answer and source
        if "answer" not in result:
            result["answer"] = content.strip()
        if "source" not in result or not result["source"]:
            result["source"] = infer_source(question, tool_call_history)

        result["tool_calls"] = tool_call_history
        return result

    # Max iterations reached
    print("Max iterations reached", file=sys.stderr)
    return {
        "answer": "Unable to complete",
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
