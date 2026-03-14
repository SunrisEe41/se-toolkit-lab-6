# Task 1 Plan: Call an LLM from Code

## LLM Provider Choice

**Provider:** Qwen Code API (remote)

**Reasoning:**

- 1000 free requests per day
- Works from Russia
- No credit card required
- OpenAI-compatible API (easy integration)

**Model:** `qwen3-coder-plus` (recommended, strong tool calling capability)

**Environment Variables:**

- `LLM_API_KEY` — API key for authentication
- `LLM_API_BASE` — Base URL for the API endpoint
- `LLM_MODEL` — Model name (`qwen3-coder-plus`)

## Agent Architecture

### Data Flow

```
Command Line → Parse Args → Load Env → Call LLM → Format JSON → stdout
                                              ↓
                                          stderr (logs)
```

### Components

1. **Argument Parser**
   - Use `sys.argv[1]` to get the question
   - Exit with error to stderr if no argument provided

2. **Environment Loader**
   - Use `python-dotenv` to load `.env.agent.secret`
   - Read `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`

3. **LLM Client**
   - Use `openai` Python package (OpenAI-compatible)
   - Configure with custom `base_url` from env
   - Send single-turn chat completion request

4. **Response Formatter**
   - Extract answer from LLM response
   - Build JSON: `{"answer": "...", "tool_calls": []}`
   - Output single line to stdout via `print(json.dumps(...))`

5. **Error Handler**
   - Catch API errors, timeout errors
   - Log errors to stderr
   - Exit with non-zero code on failure

## Output Format

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

- `answer`: string (required) — the LLM's response
- `tool_calls`: array (required) — empty for Task 1

## Implementation Steps

1. [ ] Install dependencies: `openai`, `python-dotenv` (check `pyproject.toml`)
2. [ ] Create `.env.agent.secret` from `.env.agent.example`
3. [ ] Create `agent.py` with:
   - Argument parsing
   - Environment loading
   - LLM client setup
   - JSON output formatting
4. [ ] Test manually: `uv run agent.py "What does REST stand for?"`
5. [ ] Create regression test in `tests/`
6. [ ] Create `AGENT.md` documentation

## Error Handling

| Error | Handling |
|-------|----------|
| No argument provided | Print error to stderr, exit 1 |
| Missing env variables | Print error to stderr, exit 1 |
| API timeout (>60s) | Catch exception, print to stderr, exit 1 |
| API error (4xx/5xx) | Catch exception, print to stderr, exit 1 |
| Invalid JSON response | Catch exception, print to stderr, exit 1 |

## Testing Strategy

**Test:** `tests/test_task1_agent.py`

- Run `agent.py` as subprocess with a known question
- Parse stdout as JSON
- Assert `answer` key exists and is non-empty string
- Assert `tool_calls` key exists and is empty list
- Assert exit code is 0
