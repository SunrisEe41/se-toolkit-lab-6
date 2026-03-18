# Agent Documentation

## Overview

This project implements a CLI AI agent that connects to a Large Language Model (LLM) to answer questions using the project wiki documentation, source code, and the deployed backend API. The agent has an **agentic loop** that can call tools (`read_file`, `list_files`, `query_api`) to navigate the project wiki, read source code, and query the backend API.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Command Line Input                       │
│              uv run agent.py "Your question"                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Argument Parser (sys.argv)                              │
│     - Extract question from command line                    │
│     - Validate input presence                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Environment Loader (python-dotenv)                      │
│     - Load .env.agent.secret (LLM config)                   │
│     - Load .env.docker.secret (LMS API key)                 │
│     - Read LLM_API_KEY, LLM_API_BASE, LLM_MODEL             │
│     - Read LMS_API_KEY, AGENT_API_BASE_URL                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Agentic Loop                                             │
│     - Send question + tool definitions to LLM               │
│     - If tool_calls: execute tools, feed results back       │
│     - Repeat until LLM provides final answer                │
│     - Max 10 tool calls                                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Output Formatter                                         │
│     - Build JSON: {"answer": "...", "source": "...",        │
│                    "tool_calls": [...]}                     │
│     - Print single JSON line to stdout                      │
│     - Debug logs → stderr                                   │
└─────────────────────────────────────────────────────────────┘
```

## LLM Provider

**Provider:** Qwen Code API (remote)

**Model:** `qwen3-coder-plus`

**Why Qwen Code:**

- 1000 free requests per day
- Works from Russia without restrictions
- No credit card required
- OpenAI-compatible API for easy integration

**Alternative:** OpenRouter (free tier: 50 requests/day)

## Configuration

### Environment Files

The agent reads configuration from two environment files:

#### `.env.agent.secret` (LLM Configuration)

Create from template:

```bash
cp .env.agent.example .env.agent.secret
```

Required variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for LLM authentication | `sk-...` |
| `LLM_API_BASE` | Base URL of the LLM API endpoint | `http://<vm-ip>:<port>/v1` |
| `LLM_MODEL` | Model name to use | `qwen3-coder-plus` |

#### `.env.docker.secret` (Backend API Configuration)

Required variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `LMS_API_KEY` | API key for backend authentication | `my-secret-api-key` |

#### Optional Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `AGENT_API_BASE_URL` | Base URL for backend API | `http://localhost:42002` |

> **Note:** Two distinct keys:
>
> - `LMS_API_KEY` (in `.env.docker.secret`) protects your backend endpoints
> - `LLM_API_KEY` (in `.env.agent.secret`) authenticates with your LLM provider
> - **Don't mix them up!**

## Usage

### Basic Usage

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

### Expected Output (Wiki Question)

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-vscode.md#resolve-a-merge-conflict-using-vs-code",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "git-workflow.md\n..."},
    {"tool": "read_file", "args": {"path": "wiki/git-vscode.md"}, "result": "..."}
  ]
}
```

### Expected Output (API Question)

```json
{
  "answer": "There are 120 items in the database.",
  "source": "",
  "tool_calls": [
    {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}, "result": "{\"status_code\": 200, ...}"}
  ]
}
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (missing argument, config error, API error) |

### Output Streams

| Stream | Content |
|--------|---------|
| `stdout` | Valid JSON only |
| `stderr` | Debug logs, error messages |

## Implementation Details

### Dependencies

- `python-dotenv` — Environment variable loader
- `curl` — HTTP client for LLM API calls and backend API calls (used via subprocess)

### Key Functions

| Function | Purpose |
|----------|---------|
| `load_config()` | Load and validate environment variables from both .env files |
| `validate_path()` | Security check for file paths (prevent traversal) |
| `read_file()` | Read a file from the project repository |
| `list_files()` | List files in a directory |
| `query_api()` | Call the backend API with Bearer token authentication |
| `execute_tool()` | Execute a tool by name with arguments |
| `extract_source()` | Extract source reference from answer |
| `call_llm()` | Call LLM API using curl |
| `run_agentic_loop()` | Main agentic loop: LLM → tool calls → execute → repeat |
| `main()` | Entry point, orchestrates the flow |

### Tool Definitions

The agent has three tools defined as OpenAI function-calling schemas:

#### `read_file`

- **Description:** Read the contents of a file from the project repository
- **Parameters:** `path` (string, required) — relative path from project root
- **Use cases:** Wiki documentation, source code, configuration files
- **Security:** Validates path is within project directory

#### `list_files`

- **Description:** List files and directories at a given path
- **Parameters:** `path` (string, required) — relative directory path from project root
- **Use cases:** Discovering available files, exploring directory structure
- **Security:** Validates path is within project directory

#### `query_api`

- **Description:** Call the deployed backend API
- **Parameters:**
  - `method` (string, required) — HTTP method (GET, POST, etc.)
  - `path` (string, required) — API endpoint path (e.g., '/items/')
  - `body` (string, optional) — JSON request body for POST/PUT
- **Use cases:** Querying database, testing API endpoints, checking status codes
- **Authentication:** Uses `LMS_API_KEY` as Bearer token

### Agentic Loop

The agentic loop follows this pattern:

```
Question ──▶ LLM ──▶ tool calls? ──yes──▶ execute tools ──▶ back to LLM
                         │
                         no
                         │
                         ▼
                    JSON output
```

1. **Initialize:** Send system prompt + user question to LLM
2. **Check response:**
   - If `tool_calls` → execute each tool, append results as `tool` role messages, go to step 1
   - If text message → that's the final answer, extract answer + source, output JSON
3. **Limit:** Stop after 10 tool calls maximum

### System Prompt Strategy

The system prompt instructs the LLM to:

1. Choose the right tool for the question type
2. Use `list_files` first to discover relevant wiki files
3. Use `read_file` to find specific information or read source code
4. Use `query_api` for data queries and API testing
5. Include the source as `wiki/filename.md#section-anchor` for wiki answers
6. Make at most 10 tool calls
7. Keep answers concise and accurate

### Tool Selection Guidelines

The system prompt provides clear guidance on when to use each tool:

| Question Type | Tool to Use | Example |
|--------------|-------------|---------|
| Wiki documentation | `list_files` → `read_file` | "According to the wiki..." |
| Source code | `read_file` | "What framework does the backend use?" |
| Database queries | `query_api` | "How many items are in the database?" |
| API behavior | `query_api` | "What status code does /items/ return?" |
| File discovery | `list_files` | "What files are in the backend?" |

### Path Security

Tools validate paths to prevent directory traversal attacks:

```python
def validate_path(relative_path: str) -> Path:
    # Reject paths with .. segments
    if ".." in relative_path.split(os.sep):
        raise ValueError(f"Path traversal detected: {relative_path}")
    
    # Resolve to absolute path
    requested_path = (PROJECT_ROOT / relative_path).resolve()
    
    # Check that resolved path is within project root
    if not str(requested_path).startswith(str(PROJECT_ROOT)):
        raise ValueError(f"Path traversal detected: {relative_path}")
    
    return requested_path
```

### API Authentication

The `query_api` tool authenticates with the backend using a Bearer token:

```python
headers = {
    "Authorization": f"Bearer {lms_api_key}",
    "Content-Type": "application/json",
}
```

The `LMS_API_KEY` is loaded from `.env.docker.secret` — a separate file from the LLM credentials.

### Error Handling

The agent handles the following error cases:

| Error | Response |
|-------|----------|
| No question provided | Print usage to stderr, exit 1 |
| Missing env variables | Print error to stderr, exit 1 |
| Path traversal attempt | Return error message as tool result |
| File not found | Return "File not found" message |
| API error (curl fails) | Return status_code: 0 with error message |
| Max tool calls reached | Output best available answer |
| LLM returns null content | Handle gracefully with empty string |

## File Structure

```
se-toolkit-lab-6/
├── agent.py              # Main agent CLI with tools + agentic loop
├── .env.agent.secret     # LLM configuration (gitignored)
├── .env.docker.secret    # Backend API configuration (gitignored)
├── .env.agent.example    # LLM configuration template
├── .env.docker.example   # Backend API configuration template
├── AGENT.md              # This documentation
├── plans/
│   ├── task-1.md         # Implementation plan for Task 1
│   ├── task-2.md         # Implementation plan for Task 2
│   └── task-3.md         # Implementation plan for Task 3
└── tests/
    ├── test_task1_agent.py  # Regression tests for Task 1
    ├── test_task2_tools.py  # Regression tests for Task 2
    └── test_task3_system.py # Regression tests for Task 3
```

## Testing

Run the regression tests:

```bash
uv run pytest tests/test_task1_agent.py tests/test_task2_tools.py tests/test_task3_system.py -v
```

### Test Coverage

**Task 1 tests:**

- Valid JSON output
- `answer` field is present and non-empty
- `tool_calls` field is present

**Task 2 tests:**

- `read_file` in tool_calls for merge conflict question
- `list_files` in tool_calls for wiki files question
- `source` field contains wiki file reference

**Task 3 tests:**

- `read_file` in tool_calls for framework question
- `query_api` in tool_calls for items count question

## Benchmark Evaluation

Run the local benchmark:

```bash
uv run run_eval.py
```

The benchmark tests 10 questions across all classes:

- Wiki lookup (branch protection, SSH connection)
- System facts (web framework, API routers)
- Data queries (items count, status codes)
- Bug diagnosis (ZeroDivisionError, TypeError)
- Reasoning (request lifecycle, ETL idempotency)

### Lessons Learned

1. **Tool descriptions matter:** Initially, the LLM used `endpoint` instead of `path` for `query_api`. Adding explicit guidance ("Always use this field for the endpoint") fixed the issue.

2. **Handle LLM inconsistencies:** The LLM may use different parameter names. The `execute_tool` function now handles both `path` and `endpoint` for backwards compatibility.

3. **Source is optional:** For API queries, there's no wiki source. The `extract_source` function returns an empty string when no file source is found.

4. **Curl works reliably:** Using `curl` via subprocess instead of Python HTTP libraries ensures consistent behavior with the Qwen proxy.

5. **System prompt guidance is critical:** Clear guidelines on when to use each tool significantly improved tool selection accuracy.

## Example Sessions

### Wiki Question

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

**stdout:**

```json
{
  "answer": "To resolve a merge conflict in VS Code...",
  "source": "wiki/git-vscode.md#resolve-a-merge-conflict-using-vs-code",
  "tool_calls": [...]
}
```

### API Question

```bash
uv run agent.py "How many items are in the database?"
```

**stdout:**

```json
{
  "answer": "There are 42 items in the database.",
  "source": "",
  "tool_calls": [
    {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}, "result": "..."}
  ]
}
```

### Source Code Question

```bash
uv run agent.py "What framework does the backend use?"
```

**stdout:**

```json
{
  "answer": "The backend uses FastAPI, a modern Python web framework.",
  "source": "backend/app/main.py",
  "tool_calls": [
    {"tool": "read_file", "args": {"path": "backend/app/main.py"}, "result": "..."}
  ]
}
```
