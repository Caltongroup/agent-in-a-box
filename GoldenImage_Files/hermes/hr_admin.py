#!/usr/bin/env python3
"""
hermes/hr_admin.py — Penelope HR Admin Portal
Password-protected onboarding & offboarding workflow tracker.

Runs on port 5001 — completely separate from Penelope chat UI (port 5000).
Reads task lists from Excel spreadsheets in documents/ folder.
Falls back to built-in task lists if Excel files not found.
Persists workflow instances to PocketBase for audit trail.

Usage:
    source ~/penelope_venv/bin/activate
    python3 ~/GoldenImage_Files/hermes/hr_admin.py \
        --docs /home/pi/iliad_media_group_agent/documents \
        --password iliad2026 \
        --port 5001

Set password via environment variable instead of CLI arg:
    export HR_ADMIN_PASSWORD=iliad2026
"""

import argparse
import glob
import hashlib
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import Flask, jsonify, request, Response

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# ── Config ────────────────────────────────────────────────────────────────────
PB_URL           = "http://127.0.0.1:8090"
SESSION_TTL_SECS = 3600   # 1 hour

# ── App state ─────────────────────────────────────────────────────────────────
app               = Flask(__name__)
_admin_hash       = ""
_sessions         = {}           # token → expires_timestamp
_workflows        = {}           # workflow_id → workflow_dict
_onboarding_tasks = []           # template task list
_offboarding_tasks = []          # template task list
_pb_url           = PB_URL
_pb_token         = ""           # PocketBase admin token (best-effort)
_docs_path        = ""
_state_file       = ""           # path to hr_workflows.json (set at startup)

# ── Fallback task lists (used if Excel files not readable) ────────────────────

_FALLBACK_ONBOARDING = [
    # ── Real tasks from Iliad Media Group Recruiting_Onboarding Checklist ────
    {'phase': 'Are you looking to hire?', 'task': 'Identify the position', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Are you looking to hire?', 'task': 'Request compensantion study from Ataraxis via email at Ataraxis@iliadmg.com', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Are you looking to hire?', 'task': 'Identify the compensation (including but not limited to sign on bonus)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Are you looking to hire?', 'task': 'Create Job Description', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Are you looking to hire?', 'task': 'Request approval from Darrell via email. Make sure to include the job description and compensation. CC Ataraxis@iliadmg.com & Internal HR.', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Ready to post the job?', 'task': 'Request a job posting via email to careers@iliadmg.com. Make sure to include screening questions if applicable and any additional details you would like to include in the posting.', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Ready to post the job?', 'task': 'Post the job on approved sites and send confirmation once finalized', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Selection Process', 'task': 'Sort and Select applicants', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Selection Process', 'task': 'Phone interviews', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Selection Process', 'task': 'In-person/virtual Interviews', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Selection Process', 'task': 'Group interview (if applicable)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Selection Process', 'task': 'Call references', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Selection Process', 'task': 'Gather interview notes and send to Olga for filing', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Ready to make an offer?', 'task': 'Draft offer letter - Include tentative start date and candidate contact info (Phone and email). Allow at least two weeks to get everything set up, additional time needed for out-of-state.', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Ready to make an offer?', 'task': 'Email offer letter to Ataraxis, Darrell, and Internal HR for review and approval', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Ready to make an offer?', 'task': 'Extend verbal offer to candidate', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Ready to make an offer?', 'task': 'Email offer letter to candidate and request signature or approval via email.', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Ready to make an offer?', 'task': 'Email signed offer letter to Ataraxis and Internal HR.', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Ready to make an offer?', 'task': '*Any compensation/sign on bonus renegotiation after originall offer letter must be reviewed and approved by Darrell. Email revised signed offer letter to Ataraxis and Internal HR.', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'We have a new employee!', 'task': 'Request closing the job posting to careers@iliadmg.com', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'We have a new employee!', 'task': 'Follow cordial rejection protocol (i.e. Call or email non selected candidates that had an in-person interview)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'We have a new employee!', 'task': 'Email the resumes from all applicants interviewed for the position (EEO Files) to careers@iliadmg.com', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'We have a new employee!', 'task': 'Create EEO file', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Pre-onboarding', 'task': 'Submit new hire information in JIRA (Ataraxis website) and notify Direct Supervisor', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Pre-onboarding', 'task': 'Contact new hire to start the onboarding process', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Pre-onboarding', 'task': 'Request from Ataraxis a non compete or on-air agreement (if applicable). Must have for Sales and On-air staff.', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Pre-onboarding', 'task': 'Non compete and on-air agreement: Request signature from new hire and email signed agreement to Direct Supervisor and Internal HR', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Pre-onboarding', 'task': 'Notify to Direct Supervisor and Internal HR if background check came through clear', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Pre-onboarding', 'task': "Copy of Driver's License and proof of insurance Required? If yes, collect, file, and email a copy to Olga.", 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Pre-onboarding', 'task': 'Set up new hire in Ataraxis portal.', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Pre-onboarding', 'task': 'Reach out to Direct Supervisor to confirm the access needed such as monetary entry, etc..', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Pre-onboarding', 'task': 'If hourly employee, set up Direct Supervisor with acess to approve the employee timecard. Reach out to Direct Supervisor for a review of this access.', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Pre-onboarding', 'task': 'Ensure new hire can access and navigate the Ataraxis portal and can submit hours or monetary fees', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Pre-onboarding', 'task': 'Ensure Direct Supervisor is set up to receive PTO requests via email and can aprove the request in PRO.', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Pre-onboarding', 'task': 'Send email to new hire with information regarding benefits (sign-up, start date, open enrollment deadline, etc...)', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Pre-onboarding', 'task': 'Review employee handbook with new hire', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Pre-onboarding', 'task': 'Create training timeline and material', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Send email to IT to create company email address', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Coordinate equipment, workstation, and Software needed with IT (if remote workstation, allow enough time for shipping).', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Request Keyfob and lanyard from IT (If local)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Request a phone extension and voicemail reset from IT', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Request IT to add new hire to company phone plan (if applicable)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Request an advance on wages equipment form to be sent to new hire. Request must be sent to Ataraxis and IT.', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Email advance on wage equipment form for signature and file.', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Onboarding checklist', 'task': 'Email Internal HR to request a company credit card (if applicable)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Email Internal HR to request office supplies (if needed)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Email Marketing@iliadmg.com to request business cards (if applicable)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Email Marketing@iliadmg.com to request adding the new hire to company website. Must provide First, last name, headshot and job title.', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Mail welcome card (optional)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Update master Org. Chart', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Onboarding checklist', 'task': 'Email to new hire information such as starting time, location, dress code, etc...', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Set up software logins and create a login sheet for new hire. (Coordination with other deparments may be needed)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Add new hire to company contact list and allow access to PTO and conference room calendars', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Onboarding checklist', 'task': 'Add new hire to Bday list and work anniversary list', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Onboarding checklist', 'task': 'Create work anniversary plaque for new hire', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Onboarding checklist', 'task': 'Add to All Iliad Employees List', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Onboarding checklist', 'task': 'Request from IT to add new hire to All Iliad Group distribution', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Onboarding checklist', 'task': 'Request from James and Darrell to draft and send out a press release - if applicable', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Develop performance metrics', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Onboarding checklist', 'task': 'Email ESOP Onboarding letter and Beneficiary Designation form to new hire', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Warm welcome to new hire!', 'task': '1st day at the office - Make an announcement through All Iliad Spaces', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Warm welcome to new hire!', 'task': 'Coordinate with Angie Ziebell on announcement at the upcoming monthly company meeting', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Warm welcome to new hire!', 'task': "Email Marketing@iliadmg.com to request an announcement on our Linkedin's company page", 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Warm welcome to new hire!', 'task': 'Schedule time for a tour of the office and introduce new hire to other employees in-person/zoom', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Warm welcome to new hire!', 'task': 'Email Angie Ziebell to schedule time to review with new hire our Culture deck', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Present and give a tour of company intranet (under construction)', 'task': 'Review with new hire our reimbursment request procedures (if applicable). Reimbursement Request Form', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Present and give a tour of company intranet (under construction)', 'task': 'Review with new hire our Trade request procedures.  IMG - Trade Request', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Present and give a tour of company intranet (under construction)', 'task': 'Review with new hire the company Org. chart, training plans, job description, and performance expectations.', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Present and give a tour of company intranet (under construction)', 'task': 'Explain to new hire (monthly company emails - EEO, hours due, etc...)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Present and give a tour of company intranet (under construction)', 'task': 'New hire review (Ensure all steps have been completed)', 'owner': 'Internal HR', 'dept': 'HR'},
]

_FALLBACK_OFFBOARDING = [
    # ── Real tasks from Iliad Media Group Termination/Resignation Checklist ──
    {'phase': 'Need to terminate a position?', 'task': 'Discuss termination with Darrell and Ataraxis', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Need to terminate a position?', 'task': 'Request a separation agreement, severance, etc...', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Need to terminate a position?', 'task': 'Develop Exit plan (tasks re-assigments, timeline, etc.)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Need to terminate a position?', 'task': 'Submit resignation/termination in JIRA (Ataraxis website)', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Need to terminate a position?', 'task': 'Notify Ataraxis (Autumn) of termination and final check (next payday unless request sooner - in which case the turnaround is 48 biz hrs if requested in writting)', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Need to terminate a position?', 'task': 'Coordinate with Ataraxis an in-person termination meeting (if applicable)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Need to terminate a position?', 'task': 'Coordinate with IT and/or Ataraxis to gather computer equipment and other company property (keyfob, phone, credit card, etc...)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Need to terminate a position?', 'task': 'Explain what to expect after termination (benefits) - Request personal email address', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Announce departure/Termination to All Illiad', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Send out ESOP Termination/Resignation letter (only if employee has entered the plan)', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Request from Internal HR to plan a going away party (if applicable)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Coordinate with IT to remove email and software access', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Request access removal from Nielsen (send request to Darrell)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Request from IT a voicemail reset', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Request from IT to inspect the returned equipment. If damage is reported please contact Ataraxis inmediately as we should have an Advance on wages equipment form on file.', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Remove access from Traffic software (Marketron and Vcreative) - Send request to Olga', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Remove from contact list', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Remove from B-day List', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Remove from All Iliad Employees List', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Remove from Anniversary List', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Email Marketing@iliadmg.com to request the former employee to be removed from Company website', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'For all Account Executive positions, develop a plan to notify clients', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'For all On-Air personalities, coordinate with Account Executive and Traffic Department to end/transfer endorsements', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Request from IT to remove from phone plan (if applicable)', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Remove from Ataraxis portal', 'owner': 'Ataraxis', 'dept': 'Ataraxis (PEO)'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Remove from company insurance (if applicable)', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Remove credit card access (if applicable)', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Remove from Org. Chart', 'owner': 'Internal HR', 'dept': 'HR'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Request from IT to remove former employee from All Iliad group', 'owner': 'Direct Supervisor', 'dept': 'Management'},
    {'phase': 'Termination/Resignation - checklist', 'task': 'Termination/Resignation review (Ensure all steps have been completed)', 'owner': 'Internal HR', 'dept': 'HR'},
]


# ── Excel reader ──────────────────────────────────────────────────────────────

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower().strip()).strip("_")


def _dept_from_owner(owner: str) -> str:
    """Infer department from owner/executor field."""
    o = owner.lower()
    if "supervisor" in o or "hiring manager" in o or "direct" in o:
        return "Management"
    if "ataraxis" in o:
        return "Ataraxis (PEO)"
    if o.strip() == "it":
        return "IT"
    return "HR"


def _load_excel_tasks(docs_dir: str) -> tuple:
    """Try to read tasks from Excel files in docs_dir.

    Handles the Iliad Media Group spreadsheet format:
      - Sheet named "Checklist" (or active sheet)
      - Data starts at row 9
      - Col A (index 0) = task description
      - Col E (index 4) = Executor / Owner
      - Section headers = rows where col A has text but col E is empty
      - Rows with empty col A are skipped

    Returns (onboarding_tasks, offboarding_tasks) — either list may be empty.
    """
    if not HAS_OPENPYXL or not docs_dir:
        return [], []

    onboarding, offboarding = [], []

    for path in glob.glob(os.path.join(docs_dir, "*.xlsx")):
        fname = os.path.basename(path).lower()
        is_onboard  = any(k in fname for k in ("onboard", "recruit", "new hire", "hiring"))
        is_offboard = any(k in fname for k in ("offboard", "terminat", "resign", "separation"))
        if not is_onboard and not is_offboard:
            continue

        try:
            wb = openpyxl.load_workbook(path, data_only=True)
            ws = wb["Checklist"] if "Checklist" in wb.sheetnames else wb.active

            tasks = []
            current_phase = "General"

            for row in ws.iter_rows(min_row=9, values_only=True):
                col_a = str(row[0]).strip() if row[0] else ""
                col_e = str(row[4]).strip() if len(row) > 4 and row[4] else ""

                if not col_a or col_a == "None":
                    continue

                # Skip the "Employment Start Date:" / "Executor" marker row
                if col_a.lower().startswith("employment start date") or col_a.lower() == "executor":
                    continue

                # Section header: text in col A, empty col E
                if not col_e or col_e == "None":
                    current_phase = col_a
                    continue

                tasks.append({
                    "phase": current_phase,
                    "task":  col_a,
                    "owner": col_e,
                    "dept":  _dept_from_owner(col_e),
                })

            print(f"[HR]  Loaded {len(tasks)} tasks from {fname}")
            if is_onboard:
                onboarding = tasks
            else:
                offboarding = tasks

        except Exception as e:
            print(f"[HR]  Could not read {fname}: {e}")

    return onboarding, offboarding


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def _make_token() -> str:
    return secrets.token_urlsafe(32)


def _valid_session(token: str) -> bool:
    exp = _sessions.get(token)
    if not exp:
        return False
    if datetime.now(timezone.utc).timestamp() > exp:
        _sessions.pop(token, None)
        return False
    return True


def _require_auth():
    token = request.headers.get("X-Session-Token") or request.args.get("token")
    if not token or not _valid_session(token):
        return jsonify({"error": "Unauthorized"}), 401
    return None


# ── Workflow persistence ──────────────────────────────────────────────────────

def _save_state() -> None:
    """Write all workflow state to disk so it survives restarts."""
    if not _state_file:
        return
    try:
        tmp = _state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_workflows, f, indent=2)
        os.replace(tmp, _state_file)   # atomic swap — no corruption on power loss
    except Exception as e:
        print(f"[HR]  Could not save state: {e}")


def _load_state() -> None:
    """Reload workflow state from disk on startup."""
    global _workflows
    if not _state_file or not os.path.exists(_state_file):
        return
    try:
        with open(_state_file) as f:
            _workflows = json.load(f)
        print(f"[HR]  Restored {len(_workflows)} workflow(s) from {_state_file}")
    except Exception as e:
        print(f"[HR]  Could not load saved state: {e}")


# ── PocketBase helpers ────────────────────────────────────────────────────────

def _pb_log(collection: str, record: dict) -> None:
    """Best-effort log to PocketBase — failure is silent."""
    try:
        headers = {"Authorization": f"Bearer {_pb_token}"} if _pb_token else {}
        requests.post(
            f"{_pb_url}/api/collections/{collection}/records",
            json=record,
            headers=headers,
            timeout=3,
        )
    except Exception:
        pass


def _pb_auth() -> str:
    """Authenticate to PocketBase and return admin token."""
    # Try credentials from environment
    email = os.environ.get("PB_ADMIN_EMAIL", "admin2@penelope.local")
    pw    = os.environ.get("PB_ADMIN_PASSWORD", "Penelope12345")
    try:
        r = requests.post(
            f"{_pb_url}/api/admins/auth-with-password",
            json={"identity": email, "password": pw},
            timeout=5,
        )
        return r.json().get("token", "")
    except Exception:
        return ""


# ── Workflow helpers ──────────────────────────────────────────────────────────

def _new_workflow(kind: str, employee: str) -> dict:
    """Create a fresh workflow instance from the template task list."""
    template = _onboarding_tasks if kind == "onboarding" else _offboarding_tasks
    now = datetime.now(timezone.utc).isoformat()
    wf_id = secrets.token_hex(6)
    tasks = []
    for i, t in enumerate(template):
        tasks.append({
            "id":        f"{kind[:3]}_{wf_id}_{i:03d}",
            "phase":     t["phase"],
            "task":      t["task"],
            "owner":     t["owner"],
            "dept":      t["dept"],
            "status":    "pending",
            "completed_at": None,
        })
    return {
        "id":          wf_id,
        "kind":        kind,
        "employee":    employee,
        "started_at":  now,
        "tasks":       tasks,
    }


# ── API Routes ────────────────────────────────────────────────────────────────

@app.post("/hr/auth")
def hr_auth():
    data = request.get_json(silent=True) or {}
    pw   = (data.get("password") or "").strip()
    if _hash(pw) != _admin_hash:
        return jsonify({"error": "Invalid password"}), 401
    token = _make_token()
    _sessions[token] = datetime.now(timezone.utc).timestamp() + SESSION_TTL_SECS
    return jsonify({"token": token})


@app.get("/hr/workflows")
def hr_list_workflows():
    err = _require_auth()
    if err:
        return err
    wf_list = [
        {
            "id":         wf["id"],
            "kind":       wf["kind"],
            "employee":   wf["employee"],
            "started_at": wf["started_at"],
            "total":      len(wf["tasks"]),
            "done":       sum(1 for t in wf["tasks"] if t["status"] == "complete"),
        }
        for wf in _workflows.values()
    ]
    wf_list.sort(key=lambda w: w["started_at"], reverse=True)
    return jsonify({
        "workflows": wf_list,
        "onboarding_count": len(_onboarding_tasks),
        "offboarding_count": len(_offboarding_tasks),
    })


@app.post("/hr/workflows")
def hr_start_workflow():
    err = _require_auth()
    if err:
        return err
    data     = request.get_json(silent=True) or {}
    kind     = data.get("kind", "onboarding")
    employee = (data.get("employee") or "").strip()
    if not employee:
        return jsonify({"error": "Employee name required"}), 400
    if kind not in ("onboarding", "offboarding"):
        return jsonify({"error": "kind must be onboarding or offboarding"}), 400

    wf = _new_workflow(kind, employee)
    _workflows[wf["id"]] = wf
    _save_state()

    _pb_log("hr_workflows", {
        "workflow_id": wf["id"],
        "kind":        kind,
        "employee":    employee,
        "started_at":  wf["started_at"],
        "status":      "active",
    })

    return jsonify(wf), 201


@app.get("/hr/workflows/<wf_id>")
def hr_get_workflow(wf_id):
    err = _require_auth()
    if err:
        return err
    wf = _workflows.get(wf_id)
    if not wf:
        return jsonify({"error": "Not found"}), 404
    return jsonify(wf)


@app.post("/hr/workflows/<wf_id>/tasks/<task_id>/complete")
def hr_complete_task(wf_id, task_id):
    err = _require_auth()
    if err:
        return err
    wf = _workflows.get(wf_id)
    if not wf:
        return jsonify({"error": "Workflow not found"}), 404

    task = next((t for t in wf["tasks"] if t["id"] == task_id), None)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    now = datetime.now(timezone.utc).isoformat()
    task["status"]       = "complete"
    task["completed_at"] = now
    _save_state()

    done  = sum(1 for t in wf["tasks"] if t["status"] == "complete")
    total = len(wf["tasks"])

    _pb_log("hr_task_completions", {
        "workflow_id":  wf_id,
        "task_id":      task_id,
        "task_name":    task["task"],
        "phase":        task["phase"],
        "dept":         task["dept"],
        "completed_at": now,
    })

    return jsonify({"done": done, "total": total, "task": task})


@app.post("/hr/workflows/<wf_id>/tasks/<task_id>/undo")
def hr_undo_task(wf_id, task_id):
    err = _require_auth()
    if err:
        return err
    wf = _workflows.get(wf_id)
    if not wf:
        return jsonify({"error": "Workflow not found"}), 404
    task = next((t for t in wf["tasks"] if t["id"] == task_id), None)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    task["status"]       = "pending"
    task["completed_at"] = None
    _save_state()
    done  = sum(1 for t in wf["tasks"] if t["status"] == "complete")
    return jsonify({"done": done, "total": len(wf["tasks"]), "task": task})


@app.get("/hr/health")
def hr_health():
    return jsonify({
        "status": "ok",
        "onboarding_tasks":  len(_onboarding_tasks),
        "offboarding_tasks": len(_offboarding_tasks),
        "active_workflows":  len(_workflows),
        "excel_loaded":      HAS_OPENPYXL,
    })


# ── Single-page UI ────────────────────────────────────────────────────────────

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HR Admin — Penelope</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;min-height:100vh}
header{background:#1a1a2e;color:#fff;padding:14px 24px;display:flex;align-items:center;gap:12px}
header h1{font-size:1.1rem;font-weight:600}
.dot{width:9px;height:9px;border-radius:50%;background:#4ade80;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.screen{display:none;max-width:860px;margin:40px auto;padding:0 20px}
.screen.active{display:block}
.card{background:#fff;border-radius:12px;padding:28px;box-shadow:0 1px 6px rgba(0,0,0,.08);margin-bottom:20px}
h2{font-size:1.3rem;color:#1a1a2e;margin-bottom:16px}
h3{font-size:1rem;color:#444;margin-bottom:12px;font-weight:600}
input,select{width:100%;padding:10px 14px;border:1px solid #ddd;border-radius:8px;font-size:.95rem;outline:none;font-family:inherit}
input:focus,select:focus{border-color:#1a1a2e}
.btn{display:inline-flex;align-items:center;gap:6px;padding:10px 20px;border:none;border-radius:8px;cursor:pointer;font-size:.9rem;font-weight:500;font-family:inherit;transition:.15s}
.btn-primary{background:#1a1a2e;color:#fff}.btn-primary:hover{background:#16213e}
.btn-success{background:#16a34a;color:#fff}.btn-success:hover{background:#15803d}
.btn-outline{background:#fff;color:#1a1a2e;border:1px solid #ccc}.btn-outline:hover{background:#f5f5f5}
.btn-sm{padding:6px 12px;font-size:.82rem}
.btn:disabled{opacity:.4;cursor:not-allowed}
.wf-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}
.wf-card{background:#f8fafc;border:2px solid #e2e8f0;border-radius:12px;padding:20px;cursor:pointer;transition:.15s}
.wf-card:hover{border-color:#1a1a2e;background:#fff}
.wf-card h3{font-size:1.1rem;margin-bottom:6px}
.wf-card p{font-size:.85rem;color:#666}
.wf-list{display:flex;flex-direction:column;gap:10px}
.wf-item{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px}
.wf-item .name{font-weight:600;font-size:.95rem}
.wf-item .meta{font-size:.8rem;color:#888;margin-top:2px}
.progress-wrap{background:#e5e7eb;border-radius:99px;height:8px;margin:12px 0}
.progress-bar{background:#1a1a2e;height:8px;border-radius:99px;transition:width .4s ease}
.progress-label{font-size:.82rem;color:#666;margin-bottom:4px}
.dept-filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.dept-btn{padding:5px 12px;border-radius:99px;border:1px solid #ccc;background:#fff;font-size:.8rem;cursor:pointer;transition:.15s}
.dept-btn.active{background:#1a1a2e;color:#fff;border-color:#1a1a2e}
.phase-group{margin-bottom:20px}
.phase-title{font-size:.82rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#888;margin-bottom:8px;padding-left:4px}
.task-row{display:flex;align-items:flex-start;gap:12px;padding:10px 14px;border-radius:8px;margin-bottom:6px;transition:.2s;border:1px solid transparent}
.task-row.pending{background:#f8fafc;border-color:#e2e8f0}
.task-row.complete{background:#f0fdf4;border-color:#bbf7d0;opacity:.75}
.task-info{flex:1}
.task-name{font-size:.9rem;color:#1a1a2e;line-height:1.4}
.task-name.complete{text-decoration:line-through;color:#6b7280}
.task-meta{font-size:.77rem;color:#888;margin-top:2px}
.task-actions{display:flex;gap:6px;flex-shrink:0}
.check-btn{width:28px;height:28px;border-radius:50%;border:none;cursor:pointer;font-size:.9rem;transition:.15s}
.check-btn.pending{background:#e5e7eb}.check-btn.pending:hover{background:#bbf7d0}
.check-btn.complete{background:#16a34a;color:#fff}.check-btn.complete:hover{background:#dc2626}
.err{color:#dc2626;font-size:.85rem;margin-top:8px}
.badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:.75rem;font-weight:600}
.badge-on{background:#dbeafe;color:#1e40af}
.badge-off{background:#fce7f3;color:#9d174d}
@media(max-width:600px){.wf-grid{grid-template-columns:1fr}.screen{margin:20px auto}}
</style>
</head>
<body>
<header>
  <div class="dot"></div>
  <h1>Penelope — HR Admin Portal</h1>
</header>

<!-- LOGIN -->
<div id="s-login" class="screen active">
  <div class="card" style="max-width:400px;margin:0 auto">
    <h2>Admin Login</h2>
    <p style="color:#666;font-size:.9rem;margin-bottom:20px">Enter the HR admin password to access onboarding and offboarding workflows.</p>
    <input type="password" id="pw" placeholder="Admin password" style="margin-bottom:12px">
    <button class="btn btn-primary" style="width:100%" onclick="login()">Sign In</button>
    <div id="login-err" class="err"></div>
  </div>
</div>

<!-- DASHBOARD -->
<div id="s-dash" class="screen">
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2 style="margin:0">HR Workflows</h2>
      <button class="btn btn-outline btn-sm" onclick="logout()">Sign Out</button>
    </div>
    <div class="wf-grid">
      <div class="wf-card" onclick="showNew('onboarding')">
        <h3>New Hire Onboarding</h3>
        <p id="onb-count">Loading...</p>
        <p style="margin-top:8px;color:#1a1a2e;font-weight:600">▶ Start Onboarding →</p>
      </div>
      <div class="wf-card" onclick="showNew('offboarding')">
        <h3>Employee Offboarding</h3>
        <p id="off-count">Loading...</p>
        <p style="margin-top:8px;color:#1a1a2e;font-weight:600">▶ Start Offboarding →</p>
      </div>
    </div>
    <h3>Active Workflows</h3>
    <div id="wf-list" class="wf-list">
      <p style="color:#888;font-size:.9rem">No active workflows yet.</p>
    </div>
  </div>
</div>

<!-- NEW WORKFLOW -->
<div id="s-new" class="screen">
  <div class="card" style="max-width:480px">
    <button class="btn btn-outline btn-sm" onclick="showDash()" style="margin-bottom:16px">← Back</button>
    <h2 id="new-title">Start Onboarding</h2>
    <p style="color:#666;font-size:.9rem;margin-bottom:20px">Enter the employee name to create a new workflow instance.</p>
    <input type="text" id="emp-name" placeholder="Employee full name (e.g. Jane Smith)" style="margin-bottom:12px">
    <button class="btn btn-primary" style="width:100%" onclick="startWorkflow()">Create Workflow</button>
    <div id="new-err" class="err"></div>
  </div>
</div>

<!-- WORKFLOW DETAIL -->
<div id="s-wf" class="screen">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
    <button class="btn btn-outline btn-sm" onclick="showDash()">← Dashboard</button>
    <span id="wf-badge" class="badge"></span>
    <h2 id="wf-emp" style="margin:0;flex:1"></h2>
  </div>
  <div class="card" style="padding:16px 20px">
    <div class="progress-label" id="prog-label"></div>
    <div class="progress-wrap"><div class="progress-bar" id="prog-bar"></div></div>
  </div>
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
    <span style="font-size:.85rem;color:#666">Filter by department:</span>
    <div class="dept-filters" id="dept-filters"></div>
  </div>
  <div id="task-container"></div>
</div>

<script>
let _token = null;
let _wfId  = null;
let _wfData = null;
let _activeDept = 'all';
let _newKind = 'onboarding';

async function api(method, path, body) {
  const opts = {
    method,
    headers: {'Content-Type':'application/json', 'X-Session-Token': _token || ''}
  };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
}

function show(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

async function login() {
  const pw = document.getElementById('pw').value;
  try {
    const d = await api('POST', '/hr/auth', {password: pw});
    _token = d.token;
    document.getElementById('pw').value = '';
    document.getElementById('login-err').textContent = '';
    await loadDash();
    show('s-dash');
  } catch(e) {
    document.getElementById('login-err').textContent = 'Wrong password.';
  }
}

function logout() {
  _token = null;
  show('s-login');
}

async function loadDash() {
  const d = await api('GET', '/hr/workflows');
  document.getElementById('onb-count').textContent = d.onboarding_count + ' tasks across departments';
  document.getElementById('off-count').textContent = d.offboarding_count + ' tasks across departments';
  const el = document.getElementById('wf-list');
  if (!d.workflows.length) {
    el.innerHTML = '<p style="color:#888;font-size:.9rem">No active workflows yet.</p>';
    return;
  }
  el.innerHTML = d.workflows.map(w => `
    <div class="wf-item" onclick="openWorkflow('${w.id}')" style="cursor:pointer">
      <div>
        <div class="name">${w.employee}</div>
        <div class="meta">${w.kind === 'onboarding' ? 'Onboarding' : 'Offboarding'} · Started ${new Date(w.started_at).toLocaleDateString()}</div>
      </div>
      <div style="text-align:right">
        <div style="font-size:.85rem;font-weight:600">${w.done} / ${w.total}</div>
        <div class="progress-wrap" style="width:80px;margin:4px 0 0">
          <div class="progress-bar" style="width:${Math.round(w.done/w.total*100)}%"></div>
        </div>
      </div>
    </div>
  `).join('');
}

function showDash() {
  loadDash();
  show('s-dash');
}

function showNew(kind) {
  _newKind = kind;
  document.getElementById('new-title').textContent = kind === 'onboarding' ? 'Start New Hire Onboarding' : 'Start Employee Offboarding';
  document.getElementById('emp-name').value = '';
  document.getElementById('new-err').textContent = '';
  show('s-new');
}

async function startWorkflow() {
  const emp = document.getElementById('emp-name').value.trim();
  if (!emp) { document.getElementById('new-err').textContent = 'Employee name required.'; return; }
  try {
    const wf = await api('POST', '/hr/workflows', {kind: _newKind, employee: emp});
    await openWorkflow(wf.id);
  } catch(e) {
    document.getElementById('new-err').textContent = e.message;
  }
}

async function openWorkflow(wfId) {
  _wfId = wfId;
  _activeDept = 'all';
  _wfData = await api('GET', `/hr/workflows/${wfId}`);
  renderWorkflow();
  show('s-wf');
}

function renderWorkflow() {
  const wf = _wfData;
  const done  = wf.tasks.filter(t => t.status === 'complete').length;
  const total = wf.tasks.length;
  const pct   = total ? Math.round(done / total * 100) : 0;

  document.getElementById('wf-emp').textContent = wf.employee;
  const badge = document.getElementById('wf-badge');
  badge.textContent = wf.kind === 'onboarding' ? 'Onboarding' : 'Offboarding';
  badge.className = 'badge ' + (wf.kind === 'onboarding' ? 'badge-on' : 'badge-off');
  document.getElementById('prog-label').textContent = `${done} of ${total} tasks complete (${pct}%)`;
  document.getElementById('prog-bar').style.width = pct + '%';

  // Build dept filter buttons
  const depts = ['all', ...new Set(wf.tasks.map(t => t.dept))];
  document.getElementById('dept-filters').innerHTML = depts.map(d =>
    `<button class="dept-btn${_activeDept===d?' active':''}" onclick="filterDept('${d}')">${d==='all'?'All':d}</button>`
  ).join('');

  // Group by phase
  const phases = {};
  for (const t of wf.tasks) {
    if (_activeDept !== 'all' && t.dept !== _activeDept) continue;
    (phases[t.phase] = phases[t.phase] || []).push(t);
  }

  let html = '';
  for (const [phase, tasks] of Object.entries(phases)) {
    const pDone = tasks.filter(t => t.status === 'complete').length;
    html += `<div class="phase-group">
      <div class="phase-title">${phase} — ${pDone}/${tasks.length}</div>`;
    for (const t of tasks) {
      const done = t.status === 'complete';
      html += `<div class="task-row ${t.status}" id="tr-${t.id}">
        <div class="task-info">
          <div class="task-name ${done ? 'complete' : ''}">${t.task}</div>
          <div class="task-meta">${t.owner} · ${t.dept}${done && t.completed_at ? ' · ✓ ' + new Date(t.completed_at).toLocaleString() : ''}</div>
        </div>
        <div class="task-actions">
          <button class="check-btn ${t.status}" title="${done ? 'Undo' : 'Mark complete'}"
            onclick="toggleTask('${t.id}')">${done ? '✓' : ''}</button>
        </div>
      </div>`;
    }
    html += '</div>';
  }
  document.getElementById('task-container').innerHTML = html;
}

function filterDept(dept) {
  _activeDept = dept;
  renderWorkflow();
}

async function toggleTask(taskId) {
  const task = _wfData.tasks.find(t => t.id === taskId);
  const action = task.status === 'complete' ? 'undo' : 'complete';
  try {
    const r = await api('POST', `/hr/workflows/${_wfId}/tasks/${taskId}/${action}`);
    // Update local state
    const t = _wfData.tasks.find(t => t.id === taskId);
    Object.assign(t, r.task);
    renderWorkflow();
  } catch(e) {
    alert('Error: ' + e.message);
  }
}

// Allow Enter key on login
document.getElementById('pw').addEventListener('keydown', e => {
  if (e.key === 'Enter') login();
});
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('emp-name') &&
    document.getElementById('emp-name').addEventListener('keydown', e => {
      if (e.key === 'Enter') startWorkflow();
    });
});
</script>
</body>
</html>"""


@app.get("/")
def index():
    return _HTML


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Penelope HR Admin Portal")
    parser.add_argument("--docs",     default="",          help="Path to documents/ folder (for Excel task loading)")
    parser.add_argument("--password", default="",          help="Admin password (or set HR_ADMIN_PASSWORD env var)")
    parser.add_argument("--pb-url",   default=PB_URL,      help="PocketBase URL")
    parser.add_argument("--port",     type=int, default=5001)
    parser.add_argument("--host",     default="0.0.0.0")
    args = parser.parse_args()

    # Password: CLI arg > env var > default
    raw_pw = args.password or os.environ.get("HR_ADMIN_PASSWORD", "iliad2026")
    _admin_hash = _hash(raw_pw)
    _pb_url     = args.pb_url
    _docs_path  = args.docs

    # Persist workflows to JSON next to the documents folder
    global _state_file
    _state_file = os.path.join(
        args.docs if args.docs else os.path.dirname(os.path.abspath(__file__)),
        "hr_workflows.json"
    )
    _load_state()   # restore any workflows from last run

    # Load tasks from Excel, fall back to built-ins
    xl_on, xl_off = _load_excel_tasks(_docs_path)
    _onboarding_tasks  = xl_on  if xl_on  else _FALLBACK_ONBOARDING
    _offboarding_tasks = xl_off if xl_off else _FALLBACK_OFFBOARDING

    if xl_on or xl_off:
        print(f"[HR]  Tasks loaded from Excel — onboarding: {len(_onboarding_tasks)}, offboarding: {len(_offboarding_tasks)}")
    else:
        print(f"[HR]  Using built-in task lists — onboarding: {len(_onboarding_tasks)}, offboarding: {len(_offboarding_tasks)}")
        if _docs_path:
            print(f"[HR]  (No matching Excel files found in {_docs_path})")

    # Try PocketBase auth for audit logging
    _pb_token = _pb_auth()
    if _pb_token:
        print("[HR]  PocketBase audit logging enabled.")
    else:
        print("[HR]  PocketBase auth failed — audit logging disabled (workflows still work).")

    try:
        import socket
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "<pi-ip>"

    print(f"\n{'─'*50}")
    print(f"  HR Admin Portal is running")
    print(f"  Local:    http://localhost:{args.port}")
    print(f"  Network:  http://{ip}:{args.port}")
    print(f"  Password: {'(from env var)' if os.environ.get('HR_ADMIN_PASSWORD') else raw_pw}")
    print(f"{'─'*50}\n")

    app.run(host=args.host, port=args.port, debug=False, threaded=True)
