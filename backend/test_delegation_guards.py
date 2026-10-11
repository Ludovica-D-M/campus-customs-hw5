"""Exhaustive check of the delegation loop protections.

These run without a model call, so every refusal path is exercised cheaply and
deterministically:

    .venv/bin/python backend/test_delegation_guards.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents import (  # noqa: E402
    MAX_BOSS_ESCALATIONS_PER_TICKET,
    MAX_CHAIN_DEPTH,
    MAX_DELEGATIONS_PER_TICKET,
    MAX_PEER_CONSULTS_PER_TICKET,
    check_delegation,
)

KNOWN = {"inventory", "accounting", "facilities", "customer_service"}


def check(chain, caller, who, *, delegations=0, peers=0, peer=True, escalations=0):
    return check_delegation(
        chain=chain, caller=caller, who=who, known=KNOWN,
        delegations=delegations, peer_consults=peers, peer=peer,
        escalations=escalations, escalation=(who == "boss"),
    )


CASES = [
    # (name, args, must_refuse, expected_substring)
    ("boss delegates to a specialist",
     (("boss",), "boss", "inventory"), False, ""),
    ("specialist consults a different specialist",
     (("boss", "inventory"), "inventory", "accounting"), False, ""),
    ("CYCLE: consulting someone already in the chain",
     (("boss", "accounting", "inventory"), "inventory", "accounting"), True, "would loop"),
    ("CYCLE: consulting the agent two levels up",
     (("boss", "inventory", "accounting"), "accounting", "inventory"), True, "would loop"),
    ("SELF: an agent delegating to itself",
     (("boss", "inventory"), "inventory", "inventory"), True, "cannot delegate to itself"),
    ("DEPTH: chain already at the maximum",
     (("boss", "inventory", "accounting"), "accounting", "facilities"), True, "deep"),
    ("UNKNOWN: no such agent",
     (("boss",), "boss", "legal"), True, "no agent called"),

    # Escalation runs upward and must NOT be caught by the cycle guard, even
    # though the Boss sits at the root of every chain.
    ("ESCALATE: specialist hands a question back to the Boss",
     (("boss", "inventory"), "inventory", "boss"), False, ""),
    ("ESCALATE: from inside a peer consultation",
     (("boss", "inventory"), "accounting", "boss"), False, ""),
    ("ESCALATE: refused once the chain is at maximum depth",
     (("boss", "inventory", "accounting"), "accounting", "boss"), True, "deep"),
]


def main() -> int:
    failures = 0
    print(f"limits: depth<{MAX_CHAIN_DEPTH + 1}, "
          f"delegations<={MAX_DELEGATIONS_PER_TICKET}, "
          f"peer consults<={MAX_PEER_CONSULTS_PER_TICKET}, "
          f"escalations<={MAX_BOSS_ESCALATIONS_PER_TICKET}\n")

    for name, args, must_refuse, expected in CASES:
        result = check(*args)
        refused = result is not None
        ok = refused == must_refuse and (not must_refuse or expected in str(result))
        failures += not ok
        verdict = "PASS" if ok else "FAIL"
        print(f"[{verdict}] {name}")
        if refused:
            print(f"         -> {result}")

    # The two per-ticket budgets, checked at the boundary rather than well past it.
    budget_cases = [
        ("delegation cap not yet reached",
         dict(delegations=MAX_DELEGATIONS_PER_TICKET - 1), False, ""),
        ("delegation cap reached",
         dict(delegations=MAX_DELEGATIONS_PER_TICKET), True, "delegations"),
        ("peer cap not yet reached",
         dict(peers=MAX_PEER_CONSULTS_PER_TICKET - 1), False, ""),
        ("peer cap reached",
         dict(peers=MAX_PEER_CONSULTS_PER_TICKET), True, "consulted each other"),
    ]
    for name, kwargs, must_refuse, expected in budget_cases:
        result = check(("boss", "inventory"), "inventory", "accounting", **kwargs)
        refused = result is not None
        ok = refused == must_refuse and (not must_refuse or expected in str(result))
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if refused:
            print(f"         -> {result}")

    escalation_cases = [
        ("escalation cap not yet reached",
         dict(escalations=MAX_BOSS_ESCALATIONS_PER_TICKET - 1), False, ""),
        ("escalation cap reached",
         dict(escalations=MAX_BOSS_ESCALATIONS_PER_TICKET), True, "escalated to the Boss"),
    ]
    for name, kwargs, must_refuse, expected in escalation_cases:
        result = check(("boss", "inventory"), "inventory", "boss", **kwargs)
        refused = result is not None
        ok = refused == must_refuse and (not must_refuse or expected in str(result))
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if refused:
            print(f"         -> {result}")

    # A peer cap that is spent must not block the Boss's own delegations.
    result = check(("boss",), "boss", "inventory",
                   peers=MAX_PEER_CONSULTS_PER_TICKET, peer=False)
    ok = result is None
    failures += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] peer cap does not block the Boss")

    # ...nor should a spent peer cap block an escalation, which is a different
    # budget entirely.
    result = check(("boss", "inventory"), "inventory", "boss",
                   peers=MAX_PEER_CONSULTS_PER_TICKET)
    ok = result is None
    failures += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] peer cap does not block escalation")

    print(f"\n{'all guards hold' if not failures else f'{failures} FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
