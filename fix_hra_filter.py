#!/usr/bin/env python3
"""
fix_hra_filter.py
Adds HRA keyword source filter to rag_context, same pattern as dental/vision.
Run on Pi: python3 fix_hra_filter.py
"""
from pathlib import Path

FILE = Path("/home/pi/data/web_ui.py")
text = FILE.read_text()

OLD = "        elif 'vision' in ql:\n            _where = {'source': 'vision_summary.txt'}\n            source_filter = True"

NEW = ("        elif 'vision' in ql:\n"
       "            _where = {'source': 'vision_summary.txt'}\n"
       "            source_filter = True\n"
       "        elif 'hra' in ql or 'health reimbursement' in ql or 'reimburs' in ql:\n"
       "            _where = {'source': 'hra_summary.txt'}\n"
       "            source_filter = True")

if OLD in text:
    FILE.write_text(text.replace(OLD, NEW))
    print("✓ HRA source filter added")
else:
    print("! Not found — showing vision block for inspection:")
    idx = text.find("vision_summary.txt")
    print(repr(text[idx-50:idx+150]))
