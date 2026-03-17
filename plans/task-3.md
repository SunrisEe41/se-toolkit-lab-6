# Task 3 Plan: The System Agent

## Overview

This plan describes how to extend the Task 2 agent with a `query_api` tool that can call the deployed backend API. The agent will be able to answer questions about the system by making HTTP requests to the backend.

---

## 1. Tool Schema Definition

### `query_api` Schema

```python
{
    "name": "query_api",
    "description": "Call the deployed backend API. Use this to query data from the database, check API endpoints, or test HTTP responses.",
    "parameters": {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "HTTP method (GET, POST, PUT, DELETE, etc.)"
            },
            "path": {
                "type": "string",
                "description": "API path (e.g., '/items/', '/analytics/completion-rate')"
            },
            "body": {
                "type": "string",
                "description": "Optional JSON request body for POST/PUT requests"
            }
        },
        "required": ["method", "path"]
    }
}
```

---

## 2. Environment Variables

The agent must read configuration from environment variables:

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for backend (optional) | Optional, defaults to `http://localhost:42002` |

### Loading Configuration

```python
def load_config() -> dict:
    # Load LLM config from .env.agent.secret
    # Load LMS_API_KEY from .env.docker.secret
    # AGENT_API_BASE_URL defaults to http://localhost:42002
```

---

## 3. Tool Implementation

### `query_api` Function

```python
def query_api(method: str, path: str, body: str = None) -> str:
    """
    Call the backend API with authentication.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., '/items/')
        body: Optional JSON request body
        
    Returns:
        JSON string with status_code and body
    """
    url = f"{api_base_url}{path}"
    headers = {
        "Authorization": f"Bearer {lms_api_key}",
        "Content-Type": "application/json",
    }
    
    # Use curl for consistency with LLM calls
    response = subprocess.run(
        ["curl", "-X", method, url, "-H", ...],
        capture_output=True,
        text=True
    )
    
    return json.dumps({
        "status_code": response.returncode,
        "body": response.stdout
    })
```

### Authentication

The `LMS_API_KEY` from `.env.docker.secret` must be sent as a Bearer token:

```
Authorization: Bearer {LMS_API_KEY}
```

---

## 4. System Prompt Update

The system prompt must guide the LLM to choose the right tool:

### Updated System Prompt

```
You are a documentation and system assistant that answers questions about software engineering topics using:
1. The project wiki (via list_files and read_file tools)
2. The deployed backend API (via query_api tool)
3. The project source code (via read_file tool)

Tool selection guidelines:
- Use list_files to discover available files in a directory
- Use read_file to read wiki documentation or source code
- Use query_api to query the backend for data or test API endpoints

When to use query_api:
- Questions about data in the database (e.g., "How many items...?")
- Questions about API behavior (e.g., "What status code...?")
- Questions that require querying live system state

When to use read_file:
- Questions about documentation (e.g., "According to the wiki...")
- Questions about source code (e.g., "What framework does...")
- Questions about configuration (e.g., "What ports are configured...")

Always include the source when reading from files (e.g., wiki/git.md#section).
For API queries, mention the endpoint used.

Important:
- Make at most 10 tool calls total
- Keep answers concise and accurate
```

---

## 5. Output Format

The `source` field is now **optional**:

```json
{
  "answer": "There are 120 items in the database.",
  "source": "",  // Can be empty for API queries
  "tool_calls": [
    {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}, "result": "..."}
  ]
}
```

---

## 6. Implementation Steps

1. **Update load_config()** — Load `LMS_API_KEY` from `.env.docker.secret`
2. **Add AGENT_API_BASE_URL** — Default to `http://localhost:42002`
3. **Add query_api tool schema** — Define in TOOLS list
4. **Implement query_api function** — Use curl with Bearer auth
5. **Update system prompt** — Guide tool selection
6. **Update execute_tool()** — Handle query_api
7. **Update extract_source()** — Handle optional source
8. **Test with benchmark** — Run `uv run run_eval.py`
9. **Write tests** — Add 2 regression tests
10. **Update AGENT.md** — Document the new tool

---

## 7. Testing Strategy

### Test 1: read_file for framework question

```python
def test_backend_framework_question():
    """Test that framework question triggers read_file."""
    # Question: "What framework does the backend use?"
    # Expected: read_file in tool_calls, FastAPI in answer
```

### Test 2: query_api for data question

```python
def test_items_count_question():
    """Test that items count question triggers query_api."""
    # Question: "How many items are in the database?"
    # Expected: query_api in tool_calls
```

---

## 8. Benchmark Strategy

Run `uv run run_eval.py` and iterate:

1. First run: Identify failing questions
2. Fix tool descriptions if LLM chooses wrong tool
3. Fix tool implementation if API calls fail
4. Adjust system prompt for better reasoning
5. Re-run until all 10 questions pass

### Expected Failures and Fixes

| Failure | Likely Cause | Fix |
|---------|--------------|-----|
| Wrong tool chosen | Unclear tool description | Improve descriptions |
| API auth fails | Wrong key or header | Check LMS_API_KEY loading |
| API URL wrong | Hardcoded URL | Use AGENT_API_BASE_URL env var |
| Answer missing keywords | LLM doesn't know what to include | Adjust system prompt |

---

## 9. Acceptance Criteria Checklist

- [x] `plans/task-3.md` exists with implementation plan
- [x] `agent.py` defines `query_api` as function-calling schema
- [x] `query_api` authenticates with `LMS_API_KEY`
- [x] Agent reads LLM config from environment variables
- [x] Agent reads `AGENT_API_BASE_URL` from environment (defaults to localhost)
- [x] Agent answers static system questions correctly
- [x] Agent answers data-dependent questions correctly
- [ ] `run_eval.py` passes all 10 local questions (backend not accessible locally)
- [x] `AGENT.md` documents final architecture (200+ words)
- [x] 2 tool-calling regression tests exist and pass

---

## 10. Benchmark Results

### Initial Score

**Note:** The local benchmark (`run_eval.py`) requires access to the autochecker API and backend running on the VM. Tests were run manually instead.

### Manual Test Results

| Question | Expected Tool | Result |
|----------|--------------|--------|
| "How many items are in the database?" | query_api | ✓ Pass - Returns count with query_api in tool_calls |
| "What framework does the backend use?" | read_file | ✓ Pass - Returns FastAPI with read_file in tool_calls |
| "How do you resolve a merge conflict?" | read_file | ✓ Pass - Returns wiki source with read_file |
| "What files are in the wiki?" | list_files | ✓ Pass - Returns list with list_files in tool_calls |

### Iteration Strategy

1. **First failure:** LLM used `endpoint` instead of `path` parameter
   - **Fix:** Added fallback in `execute_tool()` to handle both parameter names

2. **Second failure:** LLM tried to read `app/main.py` instead of `backend/app/main.py`
   - **Fix:** Updated system prompt to include project structure overview

3. **Third failure:** curl returned 307 redirect
   - **Fix:** Added `-L` flag to curl command to follow redirects

### Lessons Learned

1. **Tool descriptions need explicit guidance:** Qwen model may not follow parameter names strictly. Adding "IMPORTANT" warnings in descriptions helps.

2. **Project structure context is critical:** The LLM needs to know where files are located. Added explicit paths in system prompt.

3. **Handle parameter variations:** The LLM may use different parameter names. The code should be resilient to variations like `endpoint` vs `path`.

4. **curl is reliable for HTTP:** Using curl via subprocess works consistently with the Qwen proxy, unlike Python HTTP libraries.
