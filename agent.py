#!/usr/bin/env python3
"""
AI Agent CLI - Task 1: Call an LLM from Code

Usage:
    uv run agent.py "Your question here"

Output:
    JSON line to stdout: {"answer": "...", "tool_calls": []}
    All debug output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path

import dotenv
from openai import OpenAI


def load_config() -> dict:
    """Load configuration from .env.agent.secret file."""
    env_path = Path(__file__).parent / ".env.agent.secret"
    dotenv.load_dotenv(env_path)

    config = {
        "api_key": os.getenv("LLM_API_KEY"),
        "api_base": os.getenv("LLM_API_BASE"),
        "model": os.getenv("LLM_MODEL"),
    }

    # Validate required config
    missing = [key for key, value in config.items() if not value]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return config


def call_lllm(client: OpenAI, model: str, question: str) -> str:
    """Call the LLM API and return the answer."""
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": question}],
        timeout=60,
    )
    return response.choices[0].message.content


def main() -> int:
    """Main entry point."""
    # Parse command-line argument
    if len(sys.argv) < 2:
        print("Error: No question provided", file=sys.stderr)
        print("Usage: uv run agent.py \"Your question here\"", file=sys.stderr)
        return 1

    question = sys.argv[1]
    print(f"Received question: {question}", file=sys.stderr)

    # Load configuration
    try:
        config = load_config()
        print(f"Loaded config: model={config['model']}, api_base={config['api_base']}", file=sys.stderr)
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Create LLM client
    client = OpenAI(
        api_key=config["api_key"],
        base_url=config["api_base"],
    )

    # Call LLM and get answer
    try:
        answer = call_lllm(client, config["model"], question)
        print(f"Got answer from LLM", file=sys.stderr)
    except Exception as e:
        print(f"LLM API error: {e}", file=sys.stderr)
        return 1

    # Format and output JSON
    output = {
        "answer": answer,
        "tool_calls": [],
    }
    print(json.dumps(output))

    return 0


if __name__ == "__main__":
    sys.exit(main())
