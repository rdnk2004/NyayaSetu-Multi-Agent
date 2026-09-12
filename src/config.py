"""
Central Configuration Module for NyayaSetu.

Acts as a single source of truth for all operational tunables, safety limits,
model identifiers, retrieval parameters, and storage paths.

Values are dynamically read from environment variables (with support for .env files)
or fall back to established sensible defaults matching the system specifications.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure .env is loaded from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
load_dotenv()

# --- Sensible Defaults ---
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_API_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_CALLS_PER_MINUTE = 15
DEFAULT_MAX_CALLS_PER_SESSION = 200
DEFAULT_ENABLE_PROMPT_CACHE = True
DEFAULT_MAX_OUTPUT_TOKENS = 512

DEFAULT_EMBEDDING_MODEL = "multi-qa-mpnet-base-dot-v1"
DEFAULT_CHROMA_DB_PATH = PROJECT_ROOT / "data" / "chroma_db"
DEFAULT_STATUTE_COLLECTION_NAME = "legal_chunks"
DEFAULT_CASE_LAW_COLLECTION_NAME = "case_law"

DEFAULT_QA_RETRIEVAL_TOP_K = 5
DEFAULT_DEBATE_RETRIEVAL_TOP_K = 8
DEFAULT_LANDMARK_CASE_TOP_K = 3

DEFAULT_MAX_QUESTIONS = 6
DEFAULT_CHUNK_MAX_WORDS = 350


# --- Getter Functions ---
def get_gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL


def get_api_timeout_seconds() -> float:
    try:
        return float(os.environ.get("API_TIMEOUT_SECONDS", str(DEFAULT_API_TIMEOUT_SECONDS)))
    except (ValueError, TypeError):
        return DEFAULT_API_TIMEOUT_SECONDS


def get_max_calls_per_minute() -> int:
    try:
        return int(os.environ.get("MAX_CALLS_PER_MINUTE", str(DEFAULT_MAX_CALLS_PER_MINUTE)))
    except (ValueError, TypeError):
        return DEFAULT_MAX_CALLS_PER_MINUTE


def get_max_calls_per_session() -> int:
    try:
        return int(os.environ.get("MAX_CALLS_PER_SESSION", str(DEFAULT_MAX_CALLS_PER_SESSION)))
    except (ValueError, TypeError):
        return DEFAULT_MAX_CALLS_PER_SESSION


def get_enable_prompt_cache() -> bool:
    return os.environ.get("ENABLE_PROMPT_CACHE", str(DEFAULT_ENABLE_PROMPT_CACHE)).strip().lower() == "true"


def get_max_output_tokens() -> int:
    try:
        return int(os.environ.get("MAX_OUTPUT_TOKENS", str(DEFAULT_MAX_OUTPUT_TOKENS)))
    except (ValueError, TypeError):
        return DEFAULT_MAX_OUTPUT_TOKENS


def get_embedding_model() -> str:
    return os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip() or DEFAULT_EMBEDDING_MODEL


def get_chroma_db_path() -> Path:
    raw_path = os.environ.get("CHROMA_DB_PATH")
    if raw_path:
        p = Path(raw_path)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()
    return DEFAULT_CHROMA_DB_PATH


def get_statute_collection_name() -> str:
    return os.environ.get("STATUTE_COLLECTION_NAME", DEFAULT_STATUTE_COLLECTION_NAME).strip() or DEFAULT_STATUTE_COLLECTION_NAME


def get_case_law_collection_name() -> str:
    return os.environ.get("CASE_LAW_COLLECTION_NAME", DEFAULT_CASE_LAW_COLLECTION_NAME).strip() or DEFAULT_CASE_LAW_COLLECTION_NAME


def get_qa_retrieval_top_k() -> int:
    try:
        return int(os.environ.get("QA_RETRIEVAL_TOP_K", str(DEFAULT_QA_RETRIEVAL_TOP_K)))
    except (ValueError, TypeError):
        return DEFAULT_QA_RETRIEVAL_TOP_K


def get_debate_retrieval_top_k() -> int:
    try:
        return int(os.environ.get("DEBATE_RETRIEVAL_TOP_K", str(DEFAULT_DEBATE_RETRIEVAL_TOP_K)))
    except (ValueError, TypeError):
        return DEFAULT_DEBATE_RETRIEVAL_TOP_K


def get_landmark_case_top_k() -> int:
    try:
        return int(os.environ.get("LANDMARK_CASE_TOP_K", str(DEFAULT_LANDMARK_CASE_TOP_K)))
    except (ValueError, TypeError):
        return DEFAULT_LANDMARK_CASE_TOP_K


def get_max_questions() -> int:
    try:
        return int(os.environ.get("MAX_QUESTIONS", str(DEFAULT_MAX_QUESTIONS)))
    except (ValueError, TypeError):
        return DEFAULT_MAX_QUESTIONS


def get_chunk_max_words() -> int:
    try:
        return int(os.environ.get("CHUNK_MAX_WORDS", str(DEFAULT_CHUNK_MAX_WORDS)))
    except (ValueError, TypeError):
        return DEFAULT_CHUNK_MAX_WORDS


# PEP 562 module attribute lookup for dynamic synchronization with environment changes
def __getattr__(name: str):
    if name == "GEMINI_MODEL":
        return get_gemini_model()
    if name == "API_TIMEOUT_SECONDS":
        return get_api_timeout_seconds()
    if name == "MAX_CALLS_PER_MINUTE":
        return get_max_calls_per_minute()
    if name == "MAX_CALLS_PER_SESSION":
        return get_max_calls_per_session()
    if name == "ENABLE_PROMPT_CACHE":
        return get_enable_prompt_cache()
    if name == "MAX_OUTPUT_TOKENS":
        return get_max_output_tokens()
    if name == "EMBEDDING_MODEL":
        return get_embedding_model()
    if name == "CHROMA_DB_PATH":
        return get_chroma_db_path()
    if name == "STATUTE_COLLECTION_NAME":
        return get_statute_collection_name()
    if name == "CASE_LAW_COLLECTION_NAME":
        return get_case_law_collection_name()
    if name == "QA_RETRIEVAL_TOP_K":
        return get_qa_retrieval_top_k()
    if name == "DEBATE_RETRIEVAL_TOP_K":
        return get_debate_retrieval_top_k()
    if name == "LANDMARK_CASE_TOP_K":
        return get_landmark_case_top_k()
    if name == "MAX_QUESTIONS":
        return get_max_questions()
    if name == "CHUNK_MAX_WORDS":
        return get_chunk_max_words()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
