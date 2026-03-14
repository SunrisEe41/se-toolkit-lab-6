# Agent Documentation

## Overview

This project implements a CLI AI agent that connects to a Large Language Model (LLM) to answer questions. The agent serves as the foundation for more advanced features (tools, agentic loop) that will be added in subsequent tasks.

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
│  3. LLM Client (openai.OpenAI)                              │
│     - Initialize with OpenAI-compatible client              │
│     - Send chat completion request                          │
│     - Receive response from LLM                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Output Formatter                                         │
│     - Build JSON: {"answer": "...", "tool_calls": []}       │
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
uv run agent.py "What does REST stand for?"
```

### Expected Output

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
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

- `openai` — OpenAI-compatible LLM client
- `python-dotenv` — Environment variable loader

### Key Functions

| Function | Purpose |
|----------|---------|
| `load_config()` | Load and validate environment variables |
| `call_llm()` | Send request to LLM API |
| `main()` | Entry point, orchestrates the flow |

### Error Handling

The agent handles the following error cases:

| Error | Response |
|-------|----------|
| No question provided | Print usage to stderr, exit 1 |
| Missing env variables | Print error to stderr, exit 1 |
| API timeout (>60s) | Catch exception, print to stderr, exit 1 |
| API error (4xx/5xx) | Catch exception, print to stderr, exit 1 |

## File Structure

```
se-toolkit-lab-6/
├── agent.py              # Main agent CLI
├── .env.agent.secret     # LLM configuration (gitignored)
├── .env.agent.example    # Configuration template
├── AGENT.md              # This documentation
├── plans/
│   └── task-1.md         # Implementation plan
└── tests/
    └── test_task1_agent.py  # Regression tests
```

## Testing

Run the regression test:
```bash
uv run pytest tests/test_task1_agent.py -v
```

The test verifies:
- Valid JSON output
- `answer` field is present and non-empty
- `tool_calls` field is present and empty

## Future Extensions (Tasks 2-3)

- **Task 2:** Add tool support (populate `tool_calls` array)
- **Task 3:** Implement agentic loop for multi-step reasoning
