"""
Thin wrapper around the Gemini LLM API for structured extraction calls.
Both query_understanding.py and intake_agent.py call call_llm_structured(prompt)
and expect a raw JSON string back.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root directory
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
load_dotenv()


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


def call_llm_structured(prompt: str) -> str:
    """
    Send `prompt` to Gemini API and return its raw text response
    (expected to be a JSON string).
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if not api_key or api_key.strip() == "" or api_key == "your_gemini_api_key_here":
        raise ValueError(
            "GEMINI_API_KEY is missing or invalid. Please open the '.env' file in the project root "
            "and paste your Gemini API key: GEMINI_API_KEY=AIzaSy..."
        )

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    # Try official google-genai SDK first
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

    # Fallback to legacy google-generativeai SDK if installed
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        if response.text:
            return _strip_markdown_code_fences(response.text)
    except ImportError:
        pass

    # Fallback to direct HTTP REST call
    import json
    import urllib.request
    import urllib.error

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text_result = data["candidates"][0]["content"]["parts"][0]["text"]
            return _strip_markdown_code_fences(text_result)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise RuntimeError(f"Gemini API HTTP Error {e.code}: {error_body}") from e
