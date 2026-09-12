"""
Unit tests for NyayaSetu Configuration Module (src/config.py).
Verifies default values, environment variable overrides, and dynamic PEP 562 attribute resolution.
"""

import os
import sys
from pathlib import Path

# Ensure src is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import config


def test_default_config_values():
    assert config.DEFAULT_GEMINI_MODEL == "gemini-3.1-flash-lite"
    assert config.DEFAULT_API_TIMEOUT_SECONDS == 15.0
    assert config.DEFAULT_MAX_CALLS_PER_MINUTE == 15
    assert config.DEFAULT_MAX_CALLS_PER_SESSION == 200
    assert config.DEFAULT_ENABLE_PROMPT_CACHE is True
    assert config.DEFAULT_MAX_OUTPUT_TOKENS == 512
    assert config.DEFAULT_EMBEDDING_MODEL == "multi-qa-mpnet-base-dot-v1"
    assert config.DEFAULT_STATUTE_COLLECTION_NAME == "legal_chunks"
    assert config.DEFAULT_CASE_LAW_COLLECTION_NAME == "case_law"
    assert config.DEFAULT_QA_RETRIEVAL_TOP_K == 5
    assert config.DEFAULT_DEBATE_RETRIEVAL_TOP_K == 8
    assert config.DEFAULT_LANDMARK_CASE_TOP_K == 3
    assert config.DEFAULT_MAX_QUESTIONS == 6
    assert config.DEFAULT_CHUNK_MAX_WORDS == 350


def test_dynamic_env_override():
    original_session = os.environ.get("MAX_CALLS_PER_SESSION")
    original_qa_top_k = os.environ.get("QA_RETRIEVAL_TOP_K")
    original_debate_top_k = os.environ.get("DEBATE_RETRIEVAL_TOP_K")

    try:
        os.environ["MAX_CALLS_PER_SESSION"] = "99"
        assert config.MAX_CALLS_PER_SESSION == 99

        os.environ["QA_RETRIEVAL_TOP_K"] = "10"
        assert config.QA_RETRIEVAL_TOP_K == 10

        os.environ["DEBATE_RETRIEVAL_TOP_K"] = "12"
        assert config.DEBATE_RETRIEVAL_TOP_K == 12
    finally:
        if original_session is not None:
            os.environ["MAX_CALLS_PER_SESSION"] = original_session
        else:
            os.environ.pop("MAX_CALLS_PER_SESSION", None)

        if original_qa_top_k is not None:
            os.environ["QA_RETRIEVAL_TOP_K"] = original_qa_top_k
        else:
            os.environ.pop("QA_RETRIEVAL_TOP_K", None)

        if original_debate_top_k is not None:
            os.environ["DEBATE_RETRIEVAL_TOP_K"] = original_debate_top_k
        else:
            os.environ.pop("DEBATE_RETRIEVAL_TOP_K", None)


def test_top_k_separation_preserved():
    """Verify QA and Debate retrieval top_k remain distinct and not collapsed."""
    assert config.QA_RETRIEVAL_TOP_K != config.DEBATE_RETRIEVAL_TOP_K
    assert config.DEBATE_RETRIEVAL_TOP_K > config.QA_RETRIEVAL_TOP_K


if __name__ == "__main__":
    test_default_config_values()
    test_dynamic_env_override()
    test_top_k_separation_preserved()
    print("All config tests passed successfully!")
