"""
Test true negatives (out-of-scope queries) to ensure query_understanding.py
does not over-classify non-consumer disputes as Consumer Protection.
"""
import sys
import json
from pathlib import Path
import builtins

_orig_print = builtins.print
def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _orig_print(*args, **kwargs)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from query_understanding import understand_query

out_of_scope_cases = [
    {
        "id": "neg_01_landlord_tenant",
        "category": "Landlord-Tenant / Eviction",
        "message": (
            "My landlord gave me a 3-day verbal notice to vacate my rented apartment because "
            "he wants to renovate the building. I have a valid 11-month registered lease agreement "
            "and have paid rent on time every month via bank transfer. Can he legally evict me without "
            "a court decree or notice period?"
        ),
        "expected_domain": "unclear",
    },
    {
        "id": "neg_02_criminal_assault",
        "category": "Criminal Law / Street Robbery",
        "message": (
            "Yesterday evening while walking home from work, two unknown men confronted me on the street, "
            "physically assaulted me, and forcibly stole my wallet and phone. Can I lodge an FIR at the "
            "local police station for robbery and grievous hurt, and what is the police procedure?"
        ),
        "expected_domain": "unclear",
    },
    {
        "id": "neg_03_workplace_wrongful_termination",
        "category": "Employment / Labor Law (No Product)",
        "message": (
            "My company fired me yesterday without giving 30 days notice or severance pay after 3 years "
            "of continuous service as an HR manager because I refused to work unpaid overtime on weekends. "
            "Can I file a complaint before the labor commissioner or civil court for wrongful termination "
            "and recovery of unpaid wages?"
        ),
        "expected_domain": "unclear",
    },
    {
        "id": "neg_04_motor_accident_mact",
        "category": "Motor Vehicle Accident (Tort / MACT)",
        "message": (
            "A speeding private car ran a red light and crashed into my two-wheeler while I was waiting "
            "at a traffic junction, fracturing my leg. The driver had an expired driving license. "
            "Can I file a claim for medical expenses and disability compensation before the Motor Accidents "
            "Claims Tribunal (MACT)?"
        ),
        "expected_domain": "unclear",
    },
]

print("=" * 80)
print(f"TESTING TRUE NEGATIVES: OUT-OF-SCOPE DOMAIN CLASSIFICATION ({len(out_of_scope_cases)} Cases)")
print("=" * 80)

failures = 0
for case in out_of_scope_cases:
    cid = case["id"]
    cat = case["category"]
    msg = case["message"]
    exp = case["expected_domain"]

    res = understand_query(msg)
    got = res.get("domain")
    is_ok = got == exp

    status = "PASS (Correctly Unclear)" if is_ok else "FAIL (Over-permissive Leak)"
    if not is_ok:
        failures += 1

    print(f"\n[{status}] {cid} ({cat})")
    print(f"  Expected: '{exp}' | Got: '{got}'")
    if not is_ok:
        print(f"  Extracted Facts: {res.get('facts')}")

print("\n" + "=" * 80)
print(f"True-Negative Out-of-Scope Accuracy: {len(out_of_scope_cases) - failures}/{len(out_of_scope_cases)} ({((len(out_of_scope_cases) - failures)/len(out_of_scope_cases))*100:.1f}%)")
print("=" * 80)
