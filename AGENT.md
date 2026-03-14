# Agent Documentation

## Overview

This project implements a CLI AI agent that connects to a Large Language Model (LLM) to answer questions using the project wiki documentation. The agent has an **agentic loop** that can call tools (`read_file`, `list_files`) to navigate the project wiki and find answers.

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
│     - Load .env.agent.secret                                │
│     - Read LLM_API_KEY, LLM_API_BASE, LLM_MODEL             │
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

### Environment File: `.env.agent.secret`

Create from template:

```bash
cp .env.agent.example .env.agent.secret
```

Required variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for authentication | `sk-...` |
| `LLM_API_BASE` | Base URL of the API endpoint | `http://<vm-ip>:<port>/v1` |
| `LLM_MODEL` | Model name to use | `qwen3-coder-plus` |

> **Note:** This is NOT the same as `LMS_API_KEY` in `.env.docker.secret`. That key protects your backend LMS endpoints. This file configures the LLM that powers your agent.

## Usage

### Basic Usage

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

### Expected Output

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "git-workflow.md\n..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
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
- `curl` — HTTP client for LLM API calls (used via subprocess)

### Key Functions

| Function | Purpose |
|----------|---------|
| `load_config()` | Load and validate environment variables |
| `validate_path()` | Security check for file paths (prevent traversal) |
| `read_file()` | Read a file from the project repository |
| `list_files()` | List files in a directory |
| `execute_tool()` | Execute a tool by name with arguments |
| `extract_source()` | Extract source reference from answer |
| `call_llm()` | Call LLM API using curl |
| `run_agentic_loop()` | Main agentic loop: LLM → tool calls → execute → repeat |
| `main()` | Entry point, orchestrates the flow |

### Tool Definitions

The agent has two tools defined as OpenAI function-calling schemas:

#### `read_file`

- **Description:** Read the contents of a file from the project repository
- **Parameters:** `path` (string, required) — relative path from project root
- **Security:** Validates path is within project directory

#### `list_files`

- **Description:** List files and directories at a given path
- **Parameters:** `path` (string, required) — relative directory path from project root
- **Security:** Validates path is within project directory

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

1. Use `list_files` first to discover relevant wiki files
2. Use `read_file` to find specific information
3. Include the source as `wiki/filename.md#section-anchor`
4. Make at most 10 tool calls
5. Keep answers concise and accurate

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

### Error Handling

The agent handles the following error cases:

| Error | Response |
|-------|----------|
| No question provided | Print usage to stderr, exit 1 |
| Missing env variables | Print error to stderr, exit 1 |
| Path traversal attempt | Return error message as tool result |
| File not found | Return "File not found" message |
| API error (curl fails) | Print error to stderr, exit 1 |
| Max tool calls reached | Output best available answer |

## File Structure

```
se-toolkit-lab-6/
├── agent.py              # Main agent CLI with tools + agentic loop
├── .env.agent.secret     # LLM configuration (gitignored)
├── .env.agent.example    # Configuration template
├── AGENT.md              # This documentation
├── plans/
│   ├── task-1.md         # Implementation plan for Task 1
│   └── task-2.md         # Implementation plan for Task 2
└── tests/
    ├── test_task1_agent.py  # Regression tests for Task 1
    └── test_task2_tools.py  # Regression tests for Task 2
```

## Testing

Run the regression tests:

```bash
uv run pytest tests/test_task1_agent.py tests/test_task2_tools.py -v
```

### Test Coverage

**Task 1 tests:**

- Valid JSON output
- `answer` field is present and non-empty
- `tool_calls` field is present and empty (for simple questions)

**Task 2 tests:**

- `read_file` in tool_calls for merge conflict question
- `list_files` in tool_calls for wiki files question
- `source` field contains wiki file reference

## Example Session

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

**stderr output:**

```
Received question: How do you resolve a merge conflict?
Loaded config: model=qwen3-coder-plus, api_base=http://10.93.25.40:42005/v1
Starting agentic loop
LLM call (iteration 1)
Calling LLM API: http://10.93.25.40:42005/v1/chat/completions
curl exit code: 0
Executing tool: list_files with args: {'path': 'wiki'}
list_files: Listed wiki (72 entries)
LLM call (iteration 2)
Executing tool: read_file with args: {'path': 'wiki/git.md'}
read_file: Read wiki/git.md (9027 chars)
LLM call (iteration 3)
Executing tool: read_file with args: {'path': 'wiki/git-vscode.md'}
read_file: Read wiki/git-vscode.md (17861 chars)
LLM call (iteration 4)
LLM provided final answer
Extracted source: wiki/git-vscode.md#resolve-a-merge-conflict-using-vs-code
```

**stdout output:**

```json
{
  "answer": "Based on the information I found...",
  "source": "wiki/git-vscode.md#resolve-a-merge-conflict-using-vs-code",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."},
    {"tool": "read_file", "args": {"path": "wiki/git.md"}, "result": "..."},
    {"tool": "read_file", "args": {"path": "wiki/git-vscode.md"}, "result": "..."}
  ]
}
```
