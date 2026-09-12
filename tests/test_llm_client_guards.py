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
from llm_client import LLMSessionGuard


def test_prompt_caching():
    llm_client._PROMPT_CACHE.clear()
    os.environ["GEMINI_API_KEY"] = "test_key_dummy"
    os.environ["GEMINI_MODEL"] = "test_model_dummy"
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
    os.environ["GEMINI_MODEL"] = "test_model_dummy"
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


def test_independent_session_guards_budget_and_cache():
    """
    Proves two separate LLMSessionGuard instances have independent budgets and caches:
    calling the budget limit on one guard does not affect the other.
    """
    os.environ["GEMINI_API_KEY"] = "test_key_dummy"
    os.environ["GEMINI_MODEL"] = "test_model_dummy"
    os.environ["ENABLE_PROMPT_CACHE"] = "true"
    os.environ["MAX_CALLS_PER_SESSION"] = "2"

    guard_a = LLMSessionGuard()
    guard_b = LLMSessionGuard()

    # 1. Test Cache Independence
    with patch("llm_client._execute_api_call_with_retries") as mock_api:
        mock_api.side_effect = ['{"source": "guard_a"}', '{"source": "guard_b"}']

        # Call with guard_a: populates guard_a's cache
        res_a = llm_client.call_llm_structured("Shared Prompt", session_guard=guard_a)
        assert res_a == '{"source": "guard_a"}'
        assert mock_api.call_count == 1
        assert "Shared Prompt" in guard_a.prompt_cache
        assert "Shared Prompt" not in guard_b.prompt_cache

        # Same prompt with guard_b: must NOT hit guard_a's cache, should make a new API call
        res_b = llm_client.call_llm_structured("Shared Prompt", session_guard=guard_b)
        assert res_b == '{"source": "guard_b"}'
        assert mock_api.call_count == 2
        assert "Shared Prompt" in guard_b.prompt_cache

    # 2. Test Budget Independence
    # Disable cache so every subsequent call consumes from the session budget
    os.environ["ENABLE_PROMPT_CACHE"] = "false"
    with patch("llm_client._execute_api_call_with_retries", return_value='{"status": "ok"}'):
        # guard_a currently has session_call_count == 1. Call it once more to reach its limit (2)
        llm_client.call_llm_structured("prompt a2", session_guard=guard_a)
        assert guard_a.session_call_count == 2

        # 3rd call on guard_a must trigger budget protection
        try:
            llm_client.call_llm_structured("prompt a3", session_guard=guard_a)
            assert False, "guard_a should have raised RuntimeError on hitting budget limit"
        except RuntimeError as e:
            assert "Budget Protection Triggered" in str(e)

        # guard_b currently has session_call_count == 1. Calling guard_b must SUCCEED
        # because guard_a hitting its limit does not affect guard_b
        res_b_next = llm_client.call_llm_structured("prompt b2", session_guard=guard_b)
        assert res_b_next == '{"status": "ok"}'
        assert guard_b.session_call_count == 2
        print("  Independent session guards test passed: Budgets and caches are isolated.")


def test_safe_parse_llm_json():
    """Verify safe_parse_llm_json handles valid, fenced, and corrupt payloads fail-safe."""
    from llm_client import safe_parse_llm_json

    fallback = {"status": "fallback", "answer": ""}

    # 1. Valid JSON dict
    valid_res = safe_parse_llm_json('{"key": "value"}', fallback)
    assert valid_res == {"key": "value"}

    # 2. Markdown fenced JSON dict
    fenced_res = safe_parse_llm_json('```json\n{"key": "value"}\n```', fallback)
    assert fenced_res == {"key": "value"}

    # 3. Corrupt syntax returns fallback and logs warning
    with patch("llm_client.logger.warning") as mock_warn:
        corrupt_res = safe_parse_llm_json("{malformed json", fallback)
        assert corrupt_res == fallback
        assert mock_warn.called
        assert "failed to parse JSON" in mock_warn.call_args[0][0]

    # 4. Parsed JSON is not a dict (e.g. a list or string)
    with patch("llm_client.logger.warning") as mock_warn:
        list_res = safe_parse_llm_json('[1, 2, 3]', fallback)
        assert list_res == fallback
        assert mock_warn.called
        assert "not a dict" in mock_warn.call_args[0][0]

    # 5. Non-string input
    with patch("llm_client.logger.warning") as mock_warn:
        none_res = safe_parse_llm_json(None, fallback)
        assert none_res == fallback
        assert mock_warn.called
        assert "expected string response" in mock_warn.call_args[0][0]

    print("  safe_parse_llm_json tests passed: valid, fenced, corrupt, and non-dict inputs handled properly.")


if __name__ == "__main__":
    print("\nRunning LLM Client Guardrail Tests:")
    test_prompt_caching()
    test_session_limit_budget_guard()
    test_independent_session_guards_budget_and_cache()
    test_safe_parse_llm_json()
    print("\nAll guardrail tests passed successfully!")
