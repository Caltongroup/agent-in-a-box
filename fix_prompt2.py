#!/usr/bin/env python3
"""
fix_prompt2.py — replaces the RAG prompt block in web_ui.py with a strict
no-hallucination version. Run on Pi: python3 fix_prompt2.py
"""
from pathlib import Path

FILE = Path("/home/pi/data/web_ui.py")
text = FILE.read_text()

OLD = (
    '                "If the context below does not fully answer the question, first try to answer what you can from the context, then let the employee know what you couldn\'t find and ask a clarifying question to help narrow it down — for example \'Are you asking about X or Y?\' Never dead-end with \'I don\'t know\'. If the topic is sensitive or requires a decision, offer to connect them with HR. Otherwise, use ONLY the following policy excerpts to answer. "\n'
    '                "State the exact number and unit from the document in your first sentence. "\n'
    '                "Never say \'may vary\', \'typically\', \'consult HR\', or hedge in any way — the document has the answer, state it directly. "\n'
    '                "Read the question carefully. If the question asks about options or choices, list ALL of them from the context. If it asks about a specific situation, answer only that. Be concise — use bullet points for lists, 1-2 sentences for single facts.\\n\\n"'
)

NEW = (
    '                "Answer using ONLY the policy excerpts provided below. "\n'
    '                "Do NOT invent steps, portals, forms, procedures, or any information not explicitly written in the excerpts. "\n'
    '                "If the excerpts contain the answer, state it directly and concisely in 1-3 sentences. "\n'
    '                "If the excerpts do not contain enough to answer, say: I don\'t have that specific detail in my documents — please contact HR directly. "\n'
    '                "Never generate numbered steps or bullet points unless they appear word-for-word in the excerpts. "\n'
    '                "Never mention HR portals, certificates of coverage, or SBC documents unless they are named in the excerpts.\\n\\n"'
)

if OLD in text:
    text = text.replace(OLD, NEW)
    FILE.write_text(text)
    print("✓ Prompt replaced successfully")
else:
    print("! String not found — printing lines 209-214 for inspection:")
    lines = text.splitlines()
    for i, line in enumerate(lines[208:215], start=209):
        print(f"{i}: {repr(line)}")
