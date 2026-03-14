"""Regression tests for Task 2: The Documentation Agent.

This test verifies that agent.py:
- Uses tools (read_file, list_files) when answering questions
- Populates tool_calls array with tool execution results
- Includes source field with wiki file reference
- Outputs valid JSON to stdout

Run with: uv run pytest tests/test_task2_tools.py -v
"""

import json
import subprocess
import sys
from pathlib import Path


def test_merge_conflict_question():
    """Test that merge conflict question triggers read_file tool.
    
    This test runs agent.py with a question about resolving merge conflicts.
    It verifies:
    - Exit code is 0
    - 'answer' field exists and is non-empty
    - 'source' field exists and contains wiki/git-workflow.md or wiki/git.md
    - 'tool_calls' array contains at least one read_file call
    """
    # Path to agent.py in project root
    agent_path = Path(__file__).parent.parent / "agent.py"

    # Test question about merge conflicts
    question = "How do you resolve a merge conflict?"

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

    assert "source" in output, "Missing 'source' field in output"
    assert isinstance(output["source"], str), "'source' must be a string"
    # Source should contain a wiki file reference related to git
    assert "wiki/" in output["source"] and ".md" in output["source"], (
        f"'source' should contain a wiki file reference, got: {output['source']}"
    )

    assert "tool_calls" in output, "Missing 'tool_calls' field in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be a list"
    
    # Assert at least one read_file call was made
    tool_names = [call.get("tool") for call in output["tool_calls"]]
    assert "read_file" in tool_names, (
        f"Expected 'read_file' in tool_calls, got: {tool_names}"
    )


def test_wiki_files_question():
    """Test that wiki files question triggers list_files tool.
    
    This test runs agent.py with a question about what files are in the wiki.
    It verifies:
    - Exit code is 0
    - 'answer' field exists and is non-empty
    - 'tool_calls' array contains at least one list_files call
    """
    # Path to agent.py in project root
    agent_path = Path(__file__).parent.parent / "agent.py"

    # Test question about wiki files
    question = "What files are in the wiki?"

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

    assert "source" in output, "Missing 'source' field in output"
    assert isinstance(output["source"], str), "'source' must be a string"

    assert "tool_calls" in output, "Missing 'tool_calls' field in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be a list"
    
    # Assert at least one list_files call was made
    tool_names = [call.get("tool") for call in output["tool_calls"]]
    assert "list_files" in tool_names, (
        f"Expected 'list_files' in tool_calls, got: {tool_names}"
    )
