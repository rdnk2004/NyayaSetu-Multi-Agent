"""
Optimized and Cost-Aware Gemini LLM API Client.

Key Guardrails & Cost Savings:
  - Token Capping: Hard max limit on output tokens (default: 512 tokens).
  - Deterministic Output: temperature=0.0 and response_mime_type="application/json".
  - In-Memory Response Caching: Eliminates duplicate API calls for identical prompts.
  - Rate-Limiting & Quota Guard: Prevents infinite loops from consuming your API budget.
  - Exponential Backoff & Retries: Automatically handles transient network or 429 rate limit errors.
"""

import os
import time
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Tuple, List
from dotenv import load_dotenv

# Load .env file from project root directory
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
load_dotenv()


# ---------------------------------------------------------------------------
# Global In-Memory Safety & Cache Controllers
# ---------------------------------------------------------------------------
_CALL_HISTORY: List[float] = []      # Timestamps of API calls in current window
_SESSION_CALL_COUNT: int = 0         # Total calls in current application session
_PROMPT_CACHE: Dict[str, str] = {}    # Simple in-memory prompt-response cache


def _check_rate_limits() -> None:
    """
    Enforces call safety limits to protect API budget and prevent infinite loops.
    Controlled via environment variables:
      - MAX_CALLS_PER_MINUTE (default: 30)
      - MAX_CALLS_PER_SESSION (default: 200)
    """
    global _CALL_HISTORY, _SESSION_CALL_COUNT

    max_per_min = int(os.environ.get("MAX_CALLS_PER_MINUTE", "30"))
    max_per_session = int(os.environ.get("MAX_CALLS_PER_SESSION", "200"))

    # Session limit check
    if _SESSION_CALL_COUNT >= max_per_session:
        raise RuntimeError(
            f"API Budget Protection Triggered: Maximum session limit of {max_per_session} API calls reached. "
            "Halting execution to prevent quota drain. You can adjust MAX_CALLS_PER_SESSION in .env if needed."
        )

    # Rolling 60-second window check
    now = time.time()
    _CALL_HISTORY = [t for t in _CALL_HISTORY if now - t < 60.0]

    if len(_CALL_HISTORY) >= max_per_min:
        sleep_time = 60.0 - (now - _CALL_HISTORY[0])
        if sleep_time > 0:
            print(f"[LLM Guard] Rate limit window reached ({max_per_min} calls/min). Pausing for {sleep_time:.1f}s...")
            time.sleep(sleep_time)
            now = time.time()
            _CALL_HISTORY = [t for t in _CALL_HISTORY if now - t < 60.0]

    _CALL_HISTORY.append(now)
    _SESSION_CALL_COUNT += 1


def _strip_markdown_code_fences(text: str) -> str:
    """Removes ```json and ``` code block wrappers if present in LLM response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _execute_api_call_with_retries(api_key: str, model_name: str, prompt: str) -> str:
    """
    Executes Gemini API generation with retry & exponential backoff logic for transient errors.
    Uses temperature=0.0, max_output_tokens, and response_mime_type="application/json".
    """
    max_output_tokens = int(os.environ.get("MAX_OUTPUT_TOKENS", "512"))
    max_retries = int(os.environ.get("MAX_RETRIES", "3"))

    for attempt in range(1, max_retries + 1):
        try:
            # Method A: Official google-genai SDK
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=api_key)
                config = types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=max_output_tokens,
                    response_mime_type="application/json",
                )
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                if response and response.text:
                    return _strip_markdown_code_fences(response.text)
            except ImportError:
                pass

            # Method B: Legacy google-generativeai SDK
            try:
                import google.generativeai as genai

                genai.configure(api_key=api_key)
                generation_config = {
                    "temperature": 0.0,
                    "max_output_tokens": max_output_tokens,
                    "response_mime_type": "application/json",
                }
                model = genai.GenerativeModel(model_name, generation_config=generation_config)
                response = model.generate_content(prompt)
                if response and response.text:
                    return _strip_markdown_code_fences(response.text)
            except ImportError:
                pass

            # Method C: Direct HTTP REST call (Urllib)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload_dict = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": max_output_tokens,
                    "responseMimeType": "application/json",
                },
            }
            payload = json.dumps(payload_dict).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            timeout_secs = float(os.environ.get("API_TIMEOUT_SECONDS", "15.0"))
            with urllib.request.urlopen(req, timeout=timeout_secs) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text_result = data["candidates"][0]["content"]["parts"][0]["text"]
                return _strip_markdown_code_fences(text_result)

        except Exception as err:
            is_last_attempt = attempt == max_retries
            # Check for 429 rate limit or 5xx server errors
            err_str = str(err)
            if "429" in err_str or "500" in err_str or "503" in err_str or "HTTPError" in err_str or "ResourceExhausted" in err_str:
                if not is_last_attempt:
                    backoff = 2 ** (attempt - 1)
                    print(f"[LLM Guard] Transient API issue on attempt {attempt}/{max_retries}: {err}. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
            if is_last_attempt:
                raise err


def call_llm_structured(prompt: str) -> str:
    """
    Send `prompt` to Gemini API and return its raw text response
    (expected to be a JSON string).

    Includes cost optimization, caching, rate limiting, and output token limits.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if not api_key or api_key.strip() == "" or api_key == "your_gemini_api_key_here":
        raise ValueError(
            "GEMINI_API_KEY is missing or invalid. Please open the '.env' file in the project root "
            "and paste your Gemini API key: GEMINI_API_KEY=AIzaSy..."
        )

    # 1. In-Memory Cache Check (saves 100% of tokens on repeated prompts)
    enable_cache = os.environ.get("ENABLE_PROMPT_CACHE", "true").lower() in ("true", "1", "yes")
    if enable_cache and prompt in _PROMPT_CACHE:
        return _PROMPT_CACHE[prompt]

    # 2. Rate Limit & Safety Budget Check
    _check_rate_limits()

    # 3. Model Name Selection
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    # 4. API Call with Retries & Token Caps
    response_text = _execute_api_call_with_retries(api_key, model_name, prompt)

    # 5. Store in Cache
    if enable_cache:
        _PROMPT_CACHE[prompt] = response_text

    return response_text
