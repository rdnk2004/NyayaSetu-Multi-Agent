"""
Unit tests for PII Redaction Module (src/pii_redaction.py).

Verifies:
  1. Indian phone numbers (+91 prefixed, 10-digit, spaced/hyphenated) are redacted.
  2. Email addresses are redacted.
  3. Bank account and payment card sequences (8+ digits) are redacted.
  4. Personal names declared in 'my name is X' / 'I am X' patterns are redacted,
     while common non-name verbal predicates ('I am a consumer', 'I am dissatisfied')
     are preserved.
  5. Clean legal text and already-redacted text pass through unchanged.
  6. Multi-PII combined citizen messages are fully sanitized.
  7. Edge cases (None, empty string, non-string types) are handled safely.
"""

import sys
from pathlib import Path

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pii_redaction import (
    redact_pii,
    REDACTED_PHONE,
    REDACTED_EMAIL,
    REDACTED_NAME,
    REDACTED_NUMBER,
)


def test_redact_phone_numbers():
    """Verify Indian phone formats (10-digit, +91 prefixed, formatted) are redacted."""
    # 10-digit standard
    text1 = "You can call me at 9876543210 for updates."
    res1 = redact_pii(text1)
    assert REDACTED_PHONE in res1
    assert "9876543210" not in res1

    # +91 prefixed with spaces
    text2 = "My mobile is +91 98765 43210."
    res2 = redact_pii(text2)
    assert REDACTED_PHONE in res2
    assert "98765" not in res2

    # +91 prefixed with hyphens
    text3 = "Reach out on +91-98765-43210 or +919876543210."
    res3 = redact_pii(text3)
    assert res3 == f"Reach out on {REDACTED_PHONE} or {REDACTED_PHONE}."

    # Leading zero format
    text4 = "Contact: 09876543210."
    res4 = redact_pii(text4)
    assert REDACTED_PHONE in res4
    assert "09876543210" not in res4


def test_redact_email_addresses():
    """Verify email addresses with various domains and formats are redacted."""
    # Standard email
    text1 = "Please write to citizen.help@example.com."
    res1 = redact_pii(text1)
    assert res1 == f"Please write to {REDACTED_EMAIL}."

    # Subdomains and tags
    text2 = "Sent grievance to support+tag@grievance.gov.in and advocate@firm.co.in."
    res2 = redact_pii(text2)
    assert res2 == f"Sent grievance to {REDACTED_EMAIL} and {REDACTED_EMAIL}."


def test_redact_bank_account_and_card_numbers():
    """Verify 8+ digit sequences and 16-digit card numbers are redacted."""
    # 12-digit bank account
    text1 = "Refund should go to account 123456789012 at SBI."
    res1 = redact_pii(text1)
    assert REDACTED_NUMBER in res1
    assert "123456789012" not in res1

    # 8-digit minimal sequence
    text2 = "Transaction reference number is 87654321."
    res2 = redact_pii(text2)
    assert REDACTED_NUMBER in res2
    assert "87654321" not in res2

    # 16-digit card with hyphens and spaces
    text3 = "Charged my card 4111-2222-3333-4444 and 5500 1234 5678 9012."
    res3 = redact_pii(text3)
    assert res3 == f"Charged my card {REDACTED_NUMBER} and {REDACTED_NUMBER}."


def test_redact_name_declarations():
    """Verify 'my name is X' / 'I am X' name patterns are redacted."""
    # 'My name is [First] [Last]'
    text1 = "My name is Ramesh Kumar and I bought a television."
    res1 = redact_pii(text1)
    assert res1 == f"My name is {REDACTED_NAME} and I bought a television."

    # 'my name is' in lowercase
    text2 = "my name is Suresh Verma, filing against the dealer."
    res2 = redact_pii(text2)
    assert res2 == f"my name is {REDACTED_NAME}, filing against the dealer."

    # 'I am [Name]' with comma
    text3 = "I am Priya Sharma, living in Mumbai."
    res3 = redact_pii(text3)
    assert res3 == f"I am {REDACTED_NAME}, living in Mumbai."

    # 'I\'m [Name]'
    text4 = "I'm Amit Patel."
    res4 = redact_pii(text4)
    assert res4 == f"I'm {REDACTED_NAME}."

    # Honorific prefix: 'Dr. Arvind Mehta'
    text5 = "My name is Dr. Arvind Mehta."
    res5 = redact_pii(text5)
    assert res5 == f"My name is {REDACTED_NAME}."


def test_name_false_positive_guardrails():
    """Verify common non-name phrases ('I am a consumer', 'I am writing') are NOT redacted."""
    # Predicate phrase
    text1 = "I am a consumer who purchased an air conditioner."
    assert redact_pii(text1) == text1

    # Emotion / status
    text2 = "I am very dissatisfied and extremely unhappy with this delay."
    assert redact_pii(text2) == text2

    # Action
    text3 = "I am filing a complaint under the Consumer Protection Act."
    assert redact_pii(text3) == text3

    text4 = "I am unable to get a refund from the seller."
    assert redact_pii(text4) == text4


def test_clean_and_already_redacted_text_unchanged():
    """Verify clean legal text, sections, amounts, and already-redacted text are unmodified."""
    # Statutory provisions & years
    statute_text = "Under Section 35 and Section 2(11) of the Consumer Protection Act 2019."
    assert redact_pii(statute_text) == statute_text

    # Monetary amounts (5 digits)
    amount_text = "I paid Rs. 45000 for the defective device."
    assert redact_pii(amount_text) == amount_text

    # Already redacted text passes through idempotently
    already_redacted = f"User {REDACTED_NAME} with phone {REDACTED_PHONE} and email {REDACTED_EMAIL}."
    assert redact_pii(already_redacted) == already_redacted


def test_mixed_pii_combination():
    """Verify a realistic citizen narrative with all 4 PII categories is fully sanitized."""
    raw = (
        "My name is Rajesh Sharma. I can be contacted at +91 9876543210 or rajesh@lawmail.in. "
        "I transferred 75000 INR from account 987654321098 to buy a defective refrigerator."
    )
    redacted = redact_pii(raw)

    assert "Rajesh Sharma" not in redacted
    assert "+91 9876543210" not in redacted
    assert "rajesh@lawmail.in" not in redacted
    assert "987654321098" not in redacted

    assert REDACTED_NAME in redacted
    assert REDACTED_PHONE in redacted
    assert REDACTED_EMAIL in redacted
    assert REDACTED_NUMBER in redacted
    # Non-PII legal facts remain intact
    assert "75000 INR" in redacted
    assert "defective refrigerator" in redacted


def test_edge_cases_and_non_string():
    """Verify None, empty string, and non-string inputs are handled safely."""
    assert redact_pii(None) == ""
    assert redact_pii("") == ""
    assert redact_pii(12345) == "12345"
