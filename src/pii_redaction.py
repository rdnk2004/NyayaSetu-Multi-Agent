"""
PII Redaction Module for NyayaSetu.

Detects and redacts common Personally Identifiable Information (PII) patterns
in citizen-provided text BEFORE it hits logs, analytics, or persistent audit stores.

IMPORTANT DESIGN CONTRACT:
- This module is used strictly for sanitizing text prior to logging/diagnostics.
- Do NOT apply redact_pii() to prompts sent to LLMs for actual legal case processing;
  the LLM requires authentic facts to accurately assess statutory relief.
"""

import re
from typing import Any

# Standard redaction replacement tokens
REDACTED_PHONE = "[REDACTED_PHONE]"
REDACTED_EMAIL = "[REDACTED_EMAIL]"
REDACTED_NAME = "[REDACTED_NAME]"
REDACTED_NUMBER = "[REDACTED_NUMBER]"
# Alias for clarity when referencing financial/account records
REDACTED_ACCOUNT_NUMBER = REDACTED_NUMBER

# 1. Email Regex (RFC 5322-compliant standard pattern)
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# 2. Indian Phone Number Regex
# Matches Indian phone numbers in standard formats:
# - +91 prefixed (e.g. +91 9876543210, +91-98765-43210, +919876543210, +91 98765 43210)
# - Leading 0 prefixed (e.g. 09876543210)
# - 10-digit mobile numbers starting with 6, 7, 8, 9 (e.g. 9876543210, 98765-43210, 98765 43210)
# - General 10-digit numbers explicitly following +91
PHONE_REGEX = re.compile(
    r"(?<![\w\+])(?:\+91[\s.-]?|91[\s.-]|(?:\b0))?[6-9]\d{2}[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"
    r"|(?<![\w\+])(?:\+91[\s.-]?|91[\s.-]|(?:\b0))?[6-9]\d{4}[\s.-]?\d{5}(?!\d)"
    r"|(?<![\w\+])\+91[\s.-]?\d{10}(?!\d)"
    r"|(?<![\w\+])\+91[\s.-]?\d{5}[\s.-]?\d{5}(?!\d)"
)

# 3. Bank Account / Payment Card-Like Number Sequences
# Matches 8+ consecutive digits (e.g. bank account numbers 8 to 18 digits)
# as well as 16-digit credit/debit cards grouped with spaces or hyphens.
ACCOUNT_CARD_REGEX = re.compile(
    r"(?<!\d)(?:\d{4}[-\s]){3}\d{4}(?!\d)"  # 16-digit card groups (4x4)
    r"|(?<!\d)\d{8,18}(?!\d)"               # 8 to 18 consecutive digits
)

# Common words following "I am" / "My name is" that are predicates, not personal names.
_STOP_WORDS = {
    "a", "an", "the", "very", "extremely", "not", "facing", "having", "experiencing",
    "filing", "writing", "seeking", "demanding", "asking", "calling", "reporting",
    "from", "in", "at", "with", "under", "unable", "unhappy", "dissatisfied", "aggrieved",
    "consumer", "citizen", "customer", "buyer", "purchaser", "victim", "complainant",
    "ready", "done", "here", "now", "just", "also", "currently", "recently",
    "and", "or", "but", "who", "which", "that", "i", "my", "me", "we", "our", "he", "she",
    "willing", "trying", "planning", "hoping"
}

# 4. Name Detection Heuristic Pattern
#
# REGEX-BASED LIMITATION NOTE:
# Detecting full personal names via pure regular expressions is an inherent heuristic
# and best-effort approximation. In citizen text, names can vary widely across linguistic,
# cultural, and regional formats in India.
#
# This implementation specifically targets common declarative identification patterns:
#   - "My name is [Name]"
#   - "Name is [Name]"
#   - "I am [Name]"
#   - "I'm [Name]"
# with optional honorifics (Mr., Mrs., Ms., Dr., Prof.).
#
# Guardrails against false positives:
# - Common predicates ("I am a consumer", "I am very dissatisfied", "I am writing...")
#   are filtered via _STOP_WORDS.
# - For "I am", capitalized proper nouns are required to avoid masking verbal descriptors.
# - Names introduced outside declarative patterns (e.g. "Ramesh bought a laptop") or in
#   non-Latin scripts require a full NLP Named Entity Recognition (NER) model, which is
#   intentionally out-of-scope for this lightweight zero-dependency logging filter.
_NAME_PATTERN = re.compile(
    r"(?i)\b((?:my\s+name\s+is|name\s+is|i\s+am|i\'m)\s+(?:(?:mr|mrs|ms|dr|prof)\.?\s+)?)"
    r"([A-Za-z]+(?:\s+[A-Za-z]+){0,2})([.,!?;:]*)"
)


def _redact_declared_names(text: str) -> str:
    """Detect and redact names declared in 'my name is X' or 'I am X' structures."""

    def _replace_name_match(match: re.Match) -> str:
        prefix = match.group(1)
        raw_names = match.group(2)
        punct = match.group(3)
        is_i_am = bool(re.match(r"(?i)^(?:i\s+am|i\'m)", prefix.strip()))

        words = re.split(r"(\s+)", raw_names)
        valid_name_words = []
        trailing = []

        for idx in range(0, len(words), 2):
            w = words[idx]
            if w.lower() in _STOP_WORDS or w.startswith("[REDACTED"):
                trailing = words[idx - 1 :] if idx > 0 else words[idx:]
                break
            if is_i_am and not (w[0].isupper() and (len(w) == 1 or w[1:].islower())):
                trailing = words[idx - 1 :] if idx > 0 else words[idx:]
                break
            valid_name_words.append(w)
        else:
            trailing = []

        if not valid_name_words:
            return match.group(0)

        clean_prefix = re.sub(r"(?i)(?:mr|mrs|ms|dr|prof)\.?\s*$", "", prefix)
        if trailing:
            return clean_prefix + REDACTED_NAME + "".join(trailing) + punct
        return clean_prefix + REDACTED_NAME + punct

    return _NAME_PATTERN.sub(_replace_name_match, text)


def redact_pii(text: Any) -> str:
    """
    Sanitize citizen-provided text by detecting and masking common PII patterns.

    Masks:
      1. Email addresses -> [REDACTED_EMAIL]
      2. Phone numbers (Indian formats: 10-digit, +91 prefixed) -> [REDACTED_PHONE]
      3. Bank account / card-like numbers (8+ digits) -> [REDACTED_NUMBER]
      4. Names declared via 'my name is X' / 'I am X' -> [REDACTED_NAME]

    Preserves:
      - Statutory citations (e.g. 'Section 35', 'Section 2(11)')
      - Monetary values and years (e.g. 'Rs. 45,000', '2019')
      - Descriptive complaints ('I am very dissatisfied', 'I am a consumer')
      - Already redacted text (idempotent pass-through)
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return text

    # Step 1: Redact Email Addresses
    text = EMAIL_REGEX.sub(REDACTED_EMAIL, text)

    # Step 2: Redact Phone Numbers (runs before bank accounts to prevent 10-digit mobile overlap)
    text = PHONE_REGEX.sub(REDACTED_PHONE, text)

    # Step 3: Redact Bank Account / Card Sequences (8+ digits)
    text = ACCOUNT_CARD_REGEX.sub(REDACTED_NUMBER, text)

    # Step 4: Redact Declared Names (heuristic pattern)
    text = _redact_declared_names(text)

    return text
