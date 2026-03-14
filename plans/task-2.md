# Task 2 Plan: The Documentation Agent

## Overview

This plan describes how to extend the Task 1 agent with tool support and an agentic loop. The agent will be able to navigate the project wiki using `read_file` and `list_files` tools, then provide answers with source references.

---

## 1. Tool Schema Definitions

### Approach

I will define tool schemas using the OpenAI function-calling format. Each tool will have:
- `name`: The tool identifier
- `description`: What the tool does and when to use it
- `parameters`: JSON Schema defining required/optional arguments

### Tool Definitions

#### `read_file`
```python
{
    "name": "read_file",
    "description": "Read the contents of a file from the project repository. Use this to find specific information in wiki files.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')"
            }
        },
        "required": ["path"]
    }
}
```

#### `list_files`
```python
{
    "name": "list_files",
    "description": "List files and directories at a given path. Use this to discover available files in a directory.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative directory path from project root (e.g., 'wiki')"
            }
        },
        "required": ["path"]
    }
}
```

### Tool Execution Functions

I will implement two Python functions that execute the tools:

```python
def read_file(path: str) -> str:
    """Read a file from the project repository with path security."""
    
def list_files(path: str) -> str:
    """List files and directories at a given path with path security."""
```

---

## 2. Path Security

### Security Requirements

Tools must NOT access files outside the project directory. This prevents directory traversal attacks (e.g., `../../../etc/passwd`).

### Implementation Strategy

1. **Resolve to absolute path**: Use `Path.resolve()` to get the canonical absolute path
2. **Check prefix**: Verify the resolved path starts with the project root
3. **Block `..` segments**: Reject paths containing `..` before resolution

```python
def validate_path(relative_path: str) -> Path:
    """Validate that a path is within the project directory."""
    project_root = Path(__file__).parent.resolve()
    requested_path = (project_root / relative_path).resolve()
    
    # Check for path traversal
    if not str(requested_path).startswith(str(project_root)):
        raise ValueError(f"Path traversal detected: {relative_path}")
    
    return requested_path
```

### Error Handling

- If path is invalid → return error message as tool result (don't crash)
- If file doesn't exist → return "File not found: {path}"
- If path is outside project → return "Access denied: path outside project directory"

---

## 3. Agentic Loop Implementation

### Loop Structure

```
┌─────────────────────────────────────────────────────────────┐
│  1. Send user question + tool definitions to LLM            │
│  2. Check response:                                          │
│     - If tool_calls → execute tools, append results, repeat │
│     - If text message → extract answer + source, output JSON│
│  3. If 10 tool calls reached → stop and output best answer  │
└─────────────────────────────────────────────────────────────┘
```

### Message History

I will maintain a conversation history with the LLM:

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": user_question}
]
```

After each tool call:
```python
messages.append({
    "role": "assistant",
    "content": None,
    "tool_calls": response.tool_calls
})
messages.append({
    "role": "tool",
    "tool_call_id": call_id,
    "content": tool_result
})
```

### Tool Call Tracking

```python
tool_call_history = []  # List of {"tool": str, "args": dict, "result": str}
max_tool_calls = 10
```

### Loop Pseudocode

```python
def run_agentic_loop(client, model, question, tools) -> dict:
    messages = build_initial_messages(question)
    tool_call_history = []
    
    while len(tool_call_history) < max_tool_calls:
        response = call_llm(client, model, messages, tools)
        
        if response.tool_calls:
            # Execute tools
            for tool_call in response.tool_calls:
                result = execute_tool(tool_call)
                tool_call_history.append({
                    "tool": tool_call.function.name,
                    "args": json.loads(tool_call.function.arguments),
                    "result": result
                })
                # Append to messages for LLM context
                messages.append(...)
        else:
            # LLM gave final answer
            break
    
    return build_output(response.content, tool_call_history)
```

---

## 4. System Prompt Strategy

### Goals

The system prompt should instruct the LLM to:
1. Use `list_files` to discover wiki files
2. Use `read_file` to find specific information
3. Always include a `source` field with file path and section anchor
4. Stop calling tools when enough information is found

### System Prompt Draft

```
You are a documentation assistant that answers questions about software engineering topics using the project wiki.

You have access to two tools:
- list_files: List files in a directory
- read_file: Read the contents of a file

Guidelines:
1. First use list_files to discover relevant wiki files
2. Then use read_file to find specific information
3. When you have enough information, provide a concise answer
4. Always include the source as "wiki/filename.md#section-anchor"
5. Section anchors are lowercase with hyphens (e.g., #resolving-merge-conflicts)

Important:
- Make at most 10 tool calls
- If you cannot find the answer, say so
- Keep answers concise and accurate
```

---

## 5. Output Format

### JSON Structure

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

### Source Extraction

The LLM will be prompted to include the source in its response. I will:
1. Ask the LLM to format the answer with source at the end
2. Parse the response to extract source (regex or structured format)
3. If no source found, use the last read_file path as fallback

---

## 6. Implementation Steps

1. **Define tool schemas** - Add `TOOLS` list with function definitions
2. **Implement tool functions** - `read_file()` and `list_files()` with path validation
3. **Build system prompt** - Create `SYSTEM_PROMPT` constant
4. **Implement agentic loop** - `run_agentic_loop()` function
5. **Update main()** - Integrate loop, handle tool_calls in output
6. **Update AGENT.md** - Document tools, loop, and system prompt
7. **Write tests** - Add 2 regression tests for tool calling

---

## 7. Testing Strategy

### Test 1: read_file in tool_calls
```python
def test_merge_conflict_question():
    """Test that merge conflict question triggers read_file."""
    # Question: "How do you resolve a merge conflict?"
    # Expected: read_file in tool_calls, wiki/git-workflow.md in source
```

### Test 2: list_files in tool_calls
```python
def test_wiki_files_question():
    """Test that wiki files question triggers list_files."""
    # Question: "What files are in the wiki?"
    # Expected: list_files in tool_calls
```

---

## 8. Error Handling

| Error | Handling |
|-------|----------|
| Path traversal attempt | Return error message, don't execute |
| File not found | Return "File not found" message |
| LLM API error | Exit with code 1, log to stderr |
| Max tool calls reached | Output best available answer |
| No source found | Use last read file path as fallback |

---

## 9. File Structure Changes

```
se-toolkit-lab-6/
├── agent.py              # Updated with tools + agentic loop
├── AGENT.md              # Updated documentation
├── plans/
│   └── task-2.md         # This plan
└── tests/
    └── test_task1_agent.py
    └── test_task2_tools.py  # New: 2 regression tests
```

---

## 10. Acceptance Criteria Checklist

- [ ] `plans/task-2.md` exists (this file)
- [ ] `agent.py` defines `read_file` and `list_files` as tool schemas
- [ ] The agentic loop executes tool calls and feeds results back
- [ ] `tool_calls` in output is populated when tools are used
- [ ] `source` field correctly identifies wiki section
- [ ] Tools do not access files outside project directory
- [ ] `AGENT.md` documents tools and agentic loop
- [ ] 2 tool-calling regression tests exist and pass
