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

import os
import time
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
load_dotenv()

_PROMPT_CACHE: dict[str, str] = {}
_SESSION_CALL_COUNT = 0
_CALL_TIMESTAMPS: list[float] = []


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


def _enforce_rate_limit():
    global _CALL_TIMESTAMPS
    max_per_minute = int(os.environ.get("MAX_CALLS_PER_MINUTE", "30"))
    now = time.time()
    _CALL_TIMESTAMPS = [t for t in _CALL_TIMESTAMPS if now - t < 60]

    if len(_CALL_TIMESTAMPS) >= max_per_minute:
        oldest = _CALL_TIMESTAMPS[0]
        wait_time = 60 - (now - oldest)
        if wait_time > 0:
            time.sleep(wait_time)

    _CALL_TIMESTAMPS.append(time.time())


def _execute_api_call_with_retries(prompt: str, max_retries: int = 2) -> str:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    timeout = float(os.environ.get("API_TIMEOUT_SECONDS", "15.0"))

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
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
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                continue

    raise RuntimeError(f"Gemini API call failed after {max_retries + 1} attempts: {last_error}")


def call_llm_structured(prompt: str) -> str:
    global _SESSION_CALL_COUNT

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key.strip() == "" or api_key == "your_gemini_api_key_here":
        raise ValueError(
            "GEMINI_API_KEY is missing or invalid. Please open the '.env' file in the project root "
            "and paste your Gemini API key: GEMINI_API_KEY=AIzaSy..."
        )

    cache_enabled = os.environ.get("ENABLE_PROMPT_CACHE", "true").lower() == "true"
    if cache_enabled and prompt in _PROMPT_CACHE:
        return _PROMPT_CACHE[prompt]

    max_calls = int(os.environ.get("MAX_CALLS_PER_SESSION", "200"))
    if _SESSION_CALL_COUNT >= max_calls:
        raise RuntimeError(
            f"Budget Protection Triggered: this session has already made "
            f"{_SESSION_CALL_COUNT} calls, hitting MAX_CALLS_PER_SESSION={max_calls}. "
            f"Raise the limit in .env if this is intentional."
        )

    _enforce_rate_limit()

    result = _execute_api_call_with_retries(prompt)

    _SESSION_CALL_COUNT += 1
    if cache_enabled:
        _PROMPT_CACHE[prompt] = result

    return result