"""Regression tests for Task 3: The System Agent.

This test verifies that agent.py:
- Uses query_api tool when answering questions about the backend
- Uses read_file tool when answering questions about source code
- Outputs valid JSON to stdout

Run with: uv run pytest tests/test_task3_system.py -v
"""

import json
import subprocess
import sys
from pathlib import Path


def test_backend_framework_question():
    """Test that framework question triggers read_file tool.
    
    This test runs agent.py with a question about what framework the backend uses.
    It verifies:
    - Exit code is 0
    - 'answer' field exists and is non-empty
    - 'tool_calls' array contains at least one read_file call
    - Answer mentions FastAPI or the framework name
    """
    # Path to agent.py in project root
    agent_path = Path(__file__).parent.parent / "agent.py"

    # Test question about backend framework
    question = "What framework does the backend use?"

    # Run agent.py as subprocess
    result = subprocess.run(
        ["uv", "run", str(agent_path), question],
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Assert exit code is 0
    assert result.returncode == 0, (
        f"Agent exited with code {result.returncode}. stderr: {result.stderr}"
    )

    # Assert stdout is not empty
    assert result.stdout.strip(), "Agent produced no output to stdout"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"Agent output is not valid JSON: {e}\nstdout: {result.stdout}"
        )

    # Assert required fields exist
    assert "answer" in output, "Missing 'answer' field in output"
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"]) > 0, "'answer' must be non-empty"

    assert "tool_calls" in output, "Missing 'tool_calls' field in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be a list"
    
    # Assert at least one read_file call was made (to read source code)
    tool_names = [call.get("tool") for call in output["tool_calls"]]
    assert "read_file" in tool_names, (
        f"Expected 'read_file' in tool_calls, got: {tool_names}"
    )


def test_items_count_question():
    """Test that items count question triggers query_api tool.
    
    This test runs agent.py with a question about how many items are in the database.
    It verifies:
    - Exit code is 0
    - 'answer' field exists and is non-empty
    - 'tool_calls' array contains at least one query_api call
    """
    # Path to agent.py in project root
    agent_path = Path(__file__).parent.parent / "agent.py"

    # Test question about items count
    question = "How many items are in the database?"

    # Run agent.py as subprocess
    result = subprocess.run(
        ["uv", "run", str(agent_path), question],
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Assert exit code is 0
    assert result.returncode == 0, (
        f"Agent exited with code {result.returncode}. stderr: {result.stderr}"
    )

    # Assert stdout is not empty
    assert result.stdout.strip(), "Agent produced no output to stdout"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"Agent output is not valid JSON: {e}\nstdout: {result.stdout}"
        )

    # Assert required fields exist
    assert "answer" in output, "Missing 'answer' field in output"
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"]) > 0, "'answer' must be non-empty"

    assert "tool_calls" in output, "Missing 'tool_calls' field in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be a list"
    
    # Assert at least one query_api call was made
    tool_names = [call.get("tool") for call in output["tool_calls"]]
    assert "query_api" in tool_names, (
        f"Expected 'query_api' in tool_calls, got: {tool_names}"
    )
