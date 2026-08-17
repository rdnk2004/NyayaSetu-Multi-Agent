"""
Unit tests to verify rate-limiting, caching, and safety guardrails in llm_client.py.
Run: python src/test_llm_client_guards.py
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure src is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import llm_client


def test_prompt_caching():
    llm_client._PROMPT_CACHE.clear()
    os.environ["GEMINI_API_KEY"] = "test_key_dummy"
    os.environ["ENABLE_PROMPT_CACHE"] = "true"

    mock_response = '{"domain": "Consumer Protection"}'

    with patch("llm_client._execute_api_call_with_retries", return_value=mock_response) as mock_api:
        res1 = llm_client.call_llm_structured("Extract domain from message")
        res2 = llm_client.call_llm_structured("Extract domain from message")

        assert res1 == mock_response
        assert res2 == mock_response
        # API should only be called ONCE because second call was served from cache
        assert mock_api.call_count == 1
        print("  Prompt caching test passed: 100% token savings on identical prompts.")


def test_session_limit_budget_guard():
    llm_client._SESSION_CALL_COUNT = 0
    os.environ["GEMINI_API_KEY"] = "test_key_dummy"
    os.environ["MAX_CALLS_PER_SESSION"] = "2"
    os.environ["ENABLE_PROMPT_CACHE"] = "false"

    mock_response = '{"status": "ok"}'

    with patch("llm_client._execute_api_call_with_retries", return_value=mock_response):
        llm_client.call_llm_structured("prompt 1")
        llm_client.call_llm_structured("prompt 2")

        try:
            llm_client.call_llm_structured("prompt 3")
            assert False, "Should have raised RuntimeError on 3rd call exceeding session limit"
        except RuntimeError as e:
            assert "Budget Protection Triggered" in str(e)
            print("  Session limit budget guard test passed: Halts execution before quota drain.")


if __name__ == "__main__":
    print("\nRunning LLM Client Guardrail Tests:")
    test_prompt_caching()
    test_session_limit_budget_guard()
    print("\nAll guardrail tests passed successfully!")
