#!/usr/bin/env python3
"""
fix_rag_threshold.py
1. Loosens RAG distance threshold from 0.45 to 0.65 so more chunks get through.
2. Adds no-hallucination instruction to the else branch (no RAG context case).
Run on Pi: python3 fix_rag_threshold.py
"""
from pathlib import Path

FILE = Path("/home/pi/data/web_ui.py")
text = FILE.read_text()
changed = 0

# Fix 1: Loosen threshold
OLD_THRESH = "        threshold = 0.65 if source_filter else 0.45"
NEW_THRESH  = "        threshold = 0.75 if source_filter else 0.65"

if OLD_THRESH in text:
    text = text.replace(OLD_THRESH, NEW_THRESH)
    print("✓ Fixed: RAG threshold (0.45 → 0.65)")
    changed += 1
else:
    print("! Could not find threshold line")

# Fix 2: Add instructions to the no-context else branch
OLD_ELSE = (
    "        else:\n"
    "            user_content = user_message"
)
NEW_ELSE = (
    "        else:\n"
    "            user_content = (\n"
    "                \"You could not find relevant documents for this question. \"\n"
    "                \"Do NOT invent information or steps. \"\n"
    "                \"Respond only with: I don't have that specific detail in my documents — please contact HR directly. \"\n"
    "                f\"\\n\\nQuestion: {user_message}\"\n"
    "            )"
)

if OLD_ELSE in text:
    text = text.replace(OLD_ELSE, NEW_ELSE)
    print("✓ Fixed: else branch — no-hallucination fallback added")
    changed += 1
else:
    print("! Could not find else branch")

if changed > 0:
    FILE.write_text(text)
    print(f"\n✓ Saved {FILE} ({changed} change(s))")
else:
    print("\nNo changes made.")
