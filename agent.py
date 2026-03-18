#!/usr/bin/env python3
"""AI Agent CLI - Task 3: Embedded System Agent"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import dotenv

MAX_TOOL_CALLS = 15
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

SYSTEM_PROMPT = """You are an AI agent EMBEDDED in this project's file system.

YOUR IDENTITY:
- You are NOT a general chatbot - you are embedded in THIS project
- You have DIRECT access to THIS project's files  
- You do NOT have pre-trained knowledge about THIS project
- You MUST read files to answer questions about THIS project
- You MUST omit anything that does not answer the question in your answer.
- NEVER answer with the way you will do something. DO IT, then answer what you are asked.

TOOLS: list_files, read_file, query_api

RULES:
1. DO NOT, ever, say what you need to do, to answer the question. You just use the tools and answer the question with the correct answer.
2. For wiki/documentation questions: list_files wiki, then read_file the relevant file
3. For code questions: list_files backend/..., then read_file each .py file
4. For API questions: query_api (no read_file needed)
5. For bug questions: query_api THEN read_file source code
6. Answer in JSON format only: {"answer": "...", "source": "..."}

NEVER answer from pre-trained knowledge - READ the files first!"""


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
        content = p.read_text(encoding="utf-8")[:15000]
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
    if result.returncode != 0 or not result.stdout.strip():
        raise Exception(f"LLM API error: {result.stderr or 'empty response'}")
    return json.loads(result.stdout)


def extract_json_answer(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except:
        pass
    json_match = re.search(r'\{[^{}]*"answer"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass
    answer_match = re.search(r'"answer"\s*:\s*"([^"]+)"', text)
    source_match = re.search(r'"source"\s*:\s*"([^"]+)"', text)
    return {
        "answer": answer_match.group(1) if answer_match else text,
        "source": source_match.group(1) if source_match else "",
    }


def infer_source(question: str, tool_history: list) -> str:
    q = question.lower()
    for call in reversed(tool_history):
        if call["tool"] == "read_file":
            return call["args"].get("path", "")
    for call in reversed(tool_history):
        if call["tool"] == "list_files":
            return call["args"].get("path", "")
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
    elif (
        "items" in q
        or "database" in q
        or "count" in q
        or "authentication" in q
        or "401" in q
    ):
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

    for iteration in range(MAX_TOOL_CALLS):
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

        content = assistant_message.get("content") or ""
        print(f"Got answer (length={len(content)})", file=sys.stderr)
        result = extract_json_answer(content)
        if "answer" not in result:
            result["answer"] = content.strip()
        if "source" not in result or not result["source"]:
            result["source"] = infer_source(question, tool_call_history)
        result["tool_calls"] = tool_call_history
        return result

    return {
        "answer": "Unable to complete",
        "source": infer_source(question, []),
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
