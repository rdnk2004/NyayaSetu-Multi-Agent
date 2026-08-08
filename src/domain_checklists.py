"""
Domain checklists.

This is the mechanical backbone of the Intake Agent: instead of asking
an LLM "are we confident yet?" (which is an opaque vibe), we track a
fixed list of required fields per domain. Confidence = checklist full.
This makes the agent's behavior inspectable - you can always point to
exactly which field is still missing and why a follow-up was asked.

Add your second domain's checklist here once your teammate picks it -
same shape, just a new key in DOMAIN_CHECKLISTS.
"""

CONSUMER_PROTECTION_CHECKLIST = {
    "domain": "Consumer Protection",
    "fields": [
        {
            "key": "what_was_bought_or_hired",
            "prompt": "What product did you buy, or what service did you hire?",
            "required": True,
        },
        {
            "key": "what_went_wrong",
            "prompt": "What went wrong - was it defective, undelivered, "
                       "misrepresented, or something else?",
            "required": True,
        },
        {
            "key": "when_it_happened",
            "prompt": "Roughly when did this happen (purchase date or "
                       "when the issue started)?",
            "required": True,
        },
        {
            "key": "amount_paid",
            "prompt": "How much did you pay, or agree to pay, for the "
                       "goods or service?",
            "required": True,
        },
        {
            "key": "seller_or_provider",
            "prompt": "Who did you buy from or hire - a business name, "
                       "an individual, or a platform?",
            "required": True,
        },
        {
            "key": "resolution_attempted",
            "prompt": "Have you already tried contacting the seller or "
                       "provider about this? What happened?",
            "required": False,
        },
    ],
}

# Placeholder - teammate fills this in once the second domain is chosen.
# Keep the same shape as above: a "fields" list of {key, prompt, required}.
SECOND_DOMAIN_CHECKLIST = {
    "domain": "TBD",
    "fields": [],
}

DOMAIN_CHECKLISTS = {
    "Consumer Protection": CONSUMER_PROTECTION_CHECKLIST,
    # "Cyber Law": SECOND_DOMAIN_CHECKLIST,   # uncomment + fill in once chosen
}


def get_missing_required_fields(domain: str, known_facts: dict) -> list[dict]:
    """
    Given a domain and the facts collected so far, return the required
    fields that are still empty, in the order they're defined (which
    doubles as priority order - put your most important fields first
    in the checklist above).
    """
    checklist = DOMAIN_CHECKLISTS.get(domain)
    if not checklist:
        raise ValueError(f"No checklist defined for domain: {domain}")

    missing = []
    for field in checklist["fields"]:
        if not field["required"]:
            continue
        value = known_facts.get(field["key"])
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing


def is_intake_complete(domain: str, known_facts: dict) -> bool:
    """Intake is done when every required field has a non-empty value."""
    return len(get_missing_required_fields(domain, known_facts)) == 0