#!/usr/bin/env python3
"""
fix_web_ui_prompt.py
Tightens the RAG prompt in web_ui.py to prevent hallucination
and reduces NUM_PREDICT to stop rambling.
Run on the Orange Pi: python3 fix_web_ui_prompt.py
"""

from pathlib import Path

FILE = Path("/home/pi/data/web_ui.py")
text = FILE.read_text()

# Fix 1: Tighten NUM_PREDICT from 400 to 250
OLD_PREDICT = "NUM_PREDICT  = 400       # cap response tokens"
NEW_PREDICT  = "NUM_PREDICT  = 250       # cap response tokens"

# Fix 2: Replace the RAG prompt with a stricter version
OLD_PROMPT = (
    '"Answer as much as you can from the context excerpts below. '
    'If the context only partially answers the question, share what you found '
    'and ask a clarifying question to help narrow it down — for example '
    "'Are you asking about X or Y?'. "
    'Never respond with just \'I don\'t have that information\' — always try to help or redirect gracefully. '
    'For sensitive topics like discipline, termination, or medical decisions, offer to connect the employee with HR directly. '
    'Use ONLY the following policy excerpts. "'
)

NEW_PROMPT = (
    '"Answer using ONLY the policy excerpts provided below. '
    'Do NOT invent steps, procedures, portals, or information that is not explicitly stated in the excerpts. '
    'If the excerpts contain the answer, state it directly and concisely — no numbered lists unless the document uses them. '
    'If the excerpts only partially answer the question, share what you found, then ask one clarifying question. '
    'If the excerpts contain nothing relevant, say: '
    "\\\"I don't have that specific detail in my documents — please contact HR directly.\\\" "
    'Never fabricate portal names, form names, or procedures. '
    'For sensitive topics (discipline, termination, medical decisions), offer to connect the employee with HR. "'
)

fixes = [
    (OLD_PREDICT, NEW_PREDICT, "NUM_PREDICT"),
    (OLD_PROMPT,  NEW_PROMPT,  "RAG prompt"),
]

changed = 0
for old, new, label in fixes:
    if old in text:
        text = text.replace(old, new)
        print(f"✓ Fixed: {label}")
        changed += 1
    else:
        print(f"! Could not find: {label} — may already be updated")

if changed > 0:
    FILE.write_text(text)
    print(f"\n✓ Saved {FILE} ({changed} change(s))")
else:
    print("\nNo changes made.")
