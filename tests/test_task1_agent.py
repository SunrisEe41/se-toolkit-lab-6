"""Regression tests for Task 1: Call an LLM from Code.

This test verifies that agent.py:
- Outputs valid JSON to stdout
- Contains required 'answer' and 'tool_calls' fields
- Exits with code 0 on success

Run with: uv run pytest tests/test_task1_agent.py -v
"""

import json
import subprocess
import sys
from pathlib import Path


def test_agent_output_format():
    """Test that agent.py outputs valid JSON with required fields.

    This test runs agent.py as a subprocess with a simple question,
    parses the stdout as JSON, and verifies:
    - Exit code is 0
    - 'answer' field exists and is a non-empty string
    - 'tool_calls' field exists and is a list
    """
    # Path to agent.py in project root
    agent_path = Path(__file__).parent.parent / "agent.py"

    # Test question
    question = "What is 2 + 2?"

    # Run agent.py as subprocess using uv from PATH
    result = subprocess.run(
        ["uv", "run", str(agent_path), question],
        capture_output=True,
        text=True,
        timeout=60,
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

    # Assert 'answer' field exists and is non-empty string
    assert "answer" in output, "Missing 'answer' field in output"
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"]) > 0, "'answer' must be non-empty"

    # Assert 'tool_calls' field exists and is a list
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be a list"
    assert len(output["tool_calls"]) == 0, "'tool_calls' must be empty for Task 1"
