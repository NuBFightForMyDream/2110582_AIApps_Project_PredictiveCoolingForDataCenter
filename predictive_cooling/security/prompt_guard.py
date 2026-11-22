"""Prompt-injection screening of the operator question (G1) and of model-written notes (G4).

The question reaches the LLM agents as context. It cannot change numbers (Python computes them and G3 re-checks
them), but it can try to steer a model: override its instructions, call tools out of order, leak keys or claim
equipment was changed. The screen is deterministic and auditable: text is normalised first (Unicode NFKC, zero-width
and control characters removed) so look-alike or hidden characters cannot slip past, then scored against patterns.

    score 0      clean     the question is passed to the models as untrusted context
    score 1-2    flagged   the models get the default question instead; the original is kept in the case record
    score >= 3   blocked   the case stops before any agent runs (status security_alert)
"""
import os
import re
import unicodedata

FLAG_SCORE, BLOCK_SCORE = 1, 3
MAX_CHARS = 600

PATTERNS = [
    ("instruction_override", 3, r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(previous|prior|above|earlier|all|system|your|safety)\b.{0,30}"
                                r"\b(instructions?|rules?|prompts?|polic(y|ies)|guard(rail)?s?|limits?|constraints?)\b"),
    ("role_hijack", 2, r"\b(you are now|from now on you|act as (an? )?(admin|root|developer|system)|pretend (to be|you are)|"
                       r"developer mode|jailbreak|do anything now|new (system )?instructions?)\b"),
    ("secret_exfiltration", 3, r"\b(reveal|print|show|repeat|leak|output|tell me|send)\b.{0,40}\b(system prompt|instructions|"
                               r"api[ _-]?keys?|secrets?|tokens?|passwords?|credentials|env(ironment)? var)"),
    ("secret_names", 2, r"\b(GEMINI_API_KEY|ANTHROPIC_API_KEY|SUPABASE_(KEY|URL)|COMMAND_SIGNING_KEY|service[_ -]role)\b"),
    ("guard_bypass", 3, r"\b(skip|disable|bypass|turn off|switch off|deactivate|ignore)\b.{0,30}\b(g[1-4]|guards?|guardrails?|"
                        r"safety( filter)?|verification|validation|checks?|r[1-6])\b"),
    ("tool_manipulation", 2, r"\b(call|invoke|run|execute|use)\b.{0,25}\b(propose_setpoint|check_safety|finish_case|run_mpc|"
                             r"call_cooling_advisor|finish_\w+|read_equipment)\b"),
    ("limit_change", 2, r"\b(set|change|raise|increase|move)\b.{0,30}\b(limit|threshold|max(imum)?)\b.{0,25}\b(to|=)\s*\d+"),
    ("out_of_policy_setpoint", 2, r"\bset(point)?\b.{0,25}\b(to|=|at)\s*(2[5-9]|[3-9]\d|1[0-5]|[0-9])(\.\d+)?\s*(°|deg|c\b)"),
    ("actuation_request", 2, r"\b(write|send|push|apply|actuate)\b.{0,30}\b(bacnet|modbus|snmp|register|command|to the (crah|chiller))\b"),
    ("markup_or_code", 2, r"(<\s*(script|iframe|img|svg|object)\b|javascript:|```|\{\{.*\}\}|<\|.*\|>)"),
    ("encoded_payload", 2, r"([A-Za-z0-9+/]{40,}={0,2}|\b[0-9a-fA-F]{48,}\b)"),
]
COMPILED = [(name, weight, re.compile(rx, re.IGNORECASE | re.DOTALL)) for name, weight, rx in PATTERNS]
INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁤﻿­]")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalise(text: str) -> tuple[str, int]:
    """NFKC + remove zero-width/bidi/control characters. Returns (text, number of hidden characters removed)."""
    nfkc = unicodedata.normalize("NFKC", text)
    hidden = len(INVISIBLE.findall(nfkc)) + len(CONTROL.findall(nfkc))
    return CONTROL.sub("", INVISIBLE.sub("", nfkc)), hidden


def screen_question(text: str) -> dict:
    clean, hidden = normalise(text)
    matches = []
    for name, weight, rx in COMPILED:
        m = rx.search(clean)
        if m:
            matches.append({"category": name, "weight": weight, "excerpt": m.group(0)[:80]})
    if hidden:
        matches.append({"category": "hidden_characters", "weight": 2, "excerpt": f"{hidden} invisible character(s) removed"})
    if len(clean) > MAX_CHARS:
        matches.append({"category": "too_long", "weight": 1, "excerpt": f"{len(clean)} characters"})
    score = sum(m["weight"] for m in matches)
    verdict = "blocked" if score >= BLOCK_SCORE else "flagged" if score >= FLAG_SCORE else "clean"
    return {"verdict": verdict, "score": score, "matches": matches, "normalised": clean}


# ---- G4: model-written notes ------------------------------------------------------------------
SECRET_PATTERNS = [
    ("anthropic_key", r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    ("google_key", r"AIza[0-9A-Za-z_\-]{20,}"),
    ("supabase_key", r"sb_(secret|publishable)_[A-Za-z0-9_\-]{8,}"),
    ("jwt", r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}"),
    ("private_key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("url", r"\bhttps?://\S+"),
    ("email", r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
]
SECRET_ENV = ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "SUPABASE_KEY", "SUPABASE_URL", "COMMAND_SIGNING_KEY")
ACTUATION_CLAIM = re.compile(r"\b(i|we)\s+(have\s+|just\s+)?(changed|set|sent|applied|wrote|adjusted|switched)\b", re.IGNORECASE)


def screen_output(text: str) -> tuple[str, list[str]]:
    """Redact secrets, links and addresses from a model note; flag claims that equipment was changed."""
    clean, _ = normalise(text)
    found = []
    for name in SECRET_ENV:                               # the real values, if a model ever echoed one
        value = os.getenv(name, "")
        if len(value) >= 8 and value in clean:
            clean = clean.replace(value, f"[redacted:{name}]")
            found.append(f"env:{name}")
    for name, rx in SECRET_PATTERNS:
        clean, n = re.subn(rx, f"[redacted:{name}]", clean)
        found += [name] * n
    if ACTUATION_CLAIM.search(clean):
        clean += " [G4: the system cannot change equipment; this note is explanation only]"
        found.append("actuation_claim")
    return clean, found
