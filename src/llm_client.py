"""
Thin wrapper around the Gemini LLM API for structured extraction calls.
Both query_understanding.py and intake_agent.py call call_llm_structured(prompt)
and expect a raw JSON string back.

Includes cost/safety guardrails, controlled via .env:
  - ENABLE_PROMPT_CACHE   - skip the API entirely for a repeated prompt
  - MAX_CALLS_PER_SESSION - hard stop once a single run makes too many calls
  - MAX_CALLS_PER_MINUTE  - brief pause if calls are firing too fast
  - API_TIMEOUT_SECONDS   - per-request timeout
"""

import json
import logging
import os
import time
from pathlib import Path
from dotenv import load_dotenv

import config

logger = logging.getLogger(__name__)

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
load_dotenv()

class LLMSessionGuard:
    """
    Manages per-session state and safety guardrails:
      - prompt_cache: cached LLM responses keyed by prompt string
      - session_call_count: total calls made during this session
      - call_timestamps: history of call timestamps for rate limiting
    """

    def __init__(
        self,
        max_calls_per_session: int | None = None,
        max_calls_per_minute: int | None = None,
    ):
        self.prompt_cache: dict[str, str] = {}
        self.session_call_count: int = 0
        self.call_timestamps: list[float] = []
        self.max_calls_per_session: int | None = max_calls_per_session
        self.max_calls_per_minute: int | None = max_calls_per_minute

    def enforce_rate_limit(self) -> None:
        max_per_minute = (
            self.max_calls_per_minute
            if self.max_calls_per_minute is not None
            else config.MAX_CALLS_PER_MINUTE
        )
        now = time.time()
        self.call_timestamps = [t for t in self.call_timestamps if now - t < 60]

        if len(self.call_timestamps) >= max_per_minute:
            oldest = self.call_timestamps[0]
            wait_time = 60 - (now - oldest)
            if wait_time > 0:
                time.sleep(wait_time)

        self.call_timestamps.append(time.time())

    def check_budget(self) -> None:
        max_calls = (
            self.max_calls_per_session
            if self.max_calls_per_session is not None
            else config.MAX_CALLS_PER_SESSION
        )
        if self.session_call_count >= max_calls:
            raise RuntimeError(
                f"Budget Protection Triggered: this session has already made "
                f"{self.session_call_count} calls, hitting MAX_CALLS_PER_SESSION={max_calls}. "
                f"Raise the limit in .env if this is intentional."
            )

    def clear_cache(self) -> None:
        self.prompt_cache.clear()

    def reset_call_count(self) -> None:
        self.session_call_count = 0


_DEFAULT_SESSION_GUARD = LLMSessionGuard()
_PROMPT_CACHE = _DEFAULT_SESSION_GUARD.prompt_cache
_SESSION_CALL_COUNT = 0
_CALL_TIMESTAMPS = _DEFAULT_SESSION_GUARD.call_timestamps


def _strip_markdown_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def safe_parse_llm_json(raw_response: str, fallback: dict) -> dict:
    """
    Safely parses a raw LLM response into a dictionary:
    - Strips markdown code fences if present.
    - Attempts json.loads.
    - Returns parsed dict if valid, otherwise returns fallback.
    - Catches any parsing exception and returns fallback.
    - Logs a warning with a snippet of the raw response on failure.
    """
    if not isinstance(raw_response, str):
        logger.warning(
            "safe_parse_llm_json: expected string response, got %s. Falling back.",
            type(raw_response).__name__,
        )
        return fallback

    cleaned = _strip_markdown_code_fences(raw_response)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        snippet = (cleaned[:100] + "...") if len(cleaned) > 100 else cleaned
        logger.warning(
            "safe_parse_llm_json: parsed JSON is not a dict (got %s). Snippet: %s",
            type(parsed).__name__,
            snippet,
        )
        return fallback
    except Exception as e:
        snippet = (cleaned[:100] + "...") if len(cleaned) > 100 else cleaned
        logger.warning(
            "safe_parse_llm_json: failed to parse JSON: %s. Snippet: %s",
            e,
            snippet,
        )
        return fallback


_GENAI_CLIENT = None
_GENAI_CLIENT_KEY = None


def _get_genai_client(api_key: str):
    global _GENAI_CLIENT, _GENAI_CLIENT_KEY
    if _GENAI_CLIENT is None or _GENAI_CLIENT_KEY != api_key:
        from google import genai
        _GENAI_CLIENT = genai.Client(api_key=api_key)
        _GENAI_CLIENT_KEY = api_key
    return _GENAI_CLIENT


def _execute_api_call_with_retries(prompt: str, max_retries: int = 3) -> str:
    global _GENAI_CLIENT
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    model_name = config.GEMINI_MODEL
    if not model_name:
        raise ValueError(
            "GEMINI_MODEL is empty. Please set GEMINI_MODEL in your '.env' file."
        )
    timeout = config.API_TIMEOUT_SECONDS

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            try:
                client = _get_genai_client(api_key)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response.text:
                    return _strip_markdown_code_fences(response.text)
            except ImportError:
                pass

            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                if response.text:
                    return _strip_markdown_code_fences(response.text)
            except ImportError:
                pass

            import json
            import urllib.request
            import urllib.error

            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model_name}:generateContent?key={api_key}")
            payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text_result = data["candidates"][0]["content"]["parts"][0]["text"]
                return _strip_markdown_code_fences(text_result)

        except Exception as e:
            last_error = e
            err_msg = str(e)
            if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                # Quota errors won't succeed on retry - fail fast, don't burn more quota
                raise RuntimeError(f"Gemini quota exceeded, not retrying: {e}")

            # Reset client session in case socket is in a bad state
            if "10013" in err_msg or "socket" in err_msg.lower():
                _GENAI_CLIENT = None

            if attempt < max_retries:
                # Exponential backoff with longer delay for 500/503/socket errors
                backoff = 2.5 * (attempt + 1)
                time.sleep(backoff)
                continue

    raise RuntimeError(f"Gemini API call failed after {max_retries + 1} attempts: {last_error}")


def call_llm_structured(
    prompt: str,
    session_guard: LLMSessionGuard | None = None,
) -> str:
    global _SESSION_CALL_COUNT, _PROMPT_CACHE

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key.strip() == "" or api_key == "your_gemini_api_key_here":
        raise ValueError(
            "GEMINI_API_KEY is missing or invalid. Please open the '.env' file in the project root "
            "and paste your Gemini API key: GEMINI_API_KEY=AIzaSy..."
        )

    model_name = config.GEMINI_MODEL
    if not model_name:
        raise ValueError(
            "GEMINI_MODEL is empty. Please set GEMINI_MODEL in your '.env' file."
        )

    if session_guard is None:
        guard = _DEFAULT_SESSION_GUARD
        guard.session_call_count = _SESSION_CALL_COUNT
    else:
        guard = session_guard

    cache_enabled = config.ENABLE_PROMPT_CACHE
    if cache_enabled and prompt in guard.prompt_cache:
        return guard.prompt_cache[prompt]

    guard.check_budget()
    guard.enforce_rate_limit()

    result = _execute_api_call_with_retries(prompt)

    guard.session_call_count += 1
    if session_guard is None:
        _SESSION_CALL_COUNT = guard.session_call_count

    if cache_enabled:
        guard.prompt_cache[prompt] = result

    return result