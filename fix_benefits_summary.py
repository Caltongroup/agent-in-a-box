#!/usr/bin/env python3
"""
fix_benefits_summary.py
Replaces the placeholder Medicare section in benefits_summary.txt
with proper content and a disambiguation block.
Run on the Orange Pi: python3 fix_benefits_summary.py
"""

from pathlib import Path

FILE = Path("/home/pi/data/agents/iliad_media_group_agent/documents/benefits_summary.txt")

OLD = """MEDICARE REIMBURSEMENT POLICY:
A Medicare reimbursement policy is available for eligible employees. [VERIFY specific eligibility and reimbursement details with HR]"""

NEW = """MEDICARE REIMBURSEMENT POLICY (FOR EMPLOYEES ENROLLED IN MEDICARE ONLY):
This is a voluntary benefit ONLY for employees who are personally enrolled in Medicare.
It is completely separate from the HRA used by regular active employees.
Q: What is the Medicare reimbursement policy? A: Eligible employees on Medicare may submit their Medicare plan costs for reimbursement. Contact HR for eligibility requirements and the submission process.
Q: Who qualifies for Medicare reimbursement? A: Only employees personally enrolled in Medicare. Most active employees use the HRA (Health Reimbursement Arrangement) instead.
Q: How do I submit a Medicare reimbursement? A: Contact HR directly for the Medicare reimbursement form and submission instructions. Pre-approval is required.

MEDICAL REIMBURSEMENT — KNOW WHICH BENEFIT APPLIES:
Iliad Media Group has two separate medical reimbursement benefits. When an employee asks about medical reimbursement, clarify which applies:
1. HRA (Health Reimbursement Arrangement) — for ALL employees enrolled in the Iliad group medical plan. Covers deductible costs up to $1,400/year individual or $2,800/year family. Submit claims through E Benefits. Enrollment is automatic with the group health plan.
2. Medicare Reimbursement — ONLY for employees personally enrolled in Medicare. Separate voluntary benefit. Contact HR.
If the question is ambiguous, ask: "Are you asking about your HRA for regular out-of-pocket medical costs, or the Medicare reimbursement policy for employees on Medicare? They are two different benefits.\""""

text = FILE.read_text()

if OLD in text:
    text = text.replace(OLD, NEW)
    FILE.write_text(text)
    print("✓ benefits_summary.txt updated successfully")
else:
    print("! Could not find the Medicare section to replace.")
    print("  The file may have already been updated, or the text changed.")
    print("  Current Medicare section:")
    for line in text.splitlines():
        if "medicare" in line.lower():
            print(" ", line)
