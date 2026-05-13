# Claude HR Plan v1 — Onboarding & Offboarding for Penelope Demo

**Date:** April 6–7, 2026
**Status:** ✅ SHIPPED — deployed and running on Pi as of April 6 ~10 PM MT
**Author:** Claude (Cowork)

---

## What Actually Shipped (End of Day April 6)

All 5 of my differentiators were built and deployed. Here's final state:

| Item | Status |
|------|--------|
| Separate port 5001, `hr_admin.py` standalone | ✅ Running |
| Reads real Iliad Excel files via openpyxl | ✅ Working (70 onboarding, 30 offboarding tasks) |
| Named workflow instances (employee name input) | ✅ Working |
| In-place task completion, no page reload | ✅ Working |
| Department filter (Management / HR / Ataraxis PEO / IT) | ✅ Working |
| **Full disk persistence** — `hr_workflows.json`, atomic write | ✅ Added after first deploy |
| openpyxl already in venv | ✅ Pre-installed |
| hr-admin.service enabled, auto-starts on boot | ✅ Confirmed active |

**Access:** http://192.168.68.58:5001 | Password: `iliad2026`

**Persistence:** Every checkmark is written atomically to `/home/pi/iliad_media_group_agent/hr_workflows.json` the moment it's clicked. Pi can reboot and workflows resume exactly where they left off.

---

## Where I Agree With Archer

- Password + session token auth is exactly right for local Pi deployment
- PocketBase for audit trail — it's already running, use it
- The demo flow (Login → Select Workflow → Checklist → Complete) is solid
- Keep it simple for Tuesday — notifications are Week 2

---

## Where I'd Do It Differently

### 1. One file, separate port — don't touch web_ui.py

Archer adds endpoints to `rest_api_wrapper.py`. I'd keep this completely isolated:

- `hr_admin.py` runs on **port 5001**
- `web_ui.py` stays untouched on port 5000
- `hr-admin.service` systemd unit auto-starts it

**Why:** The night before a demo is the wrong time to modify a working service. If hr_admin crashes, Penelope still answers questions. If web_ui.py breaks, the whole demo is dead.

### 2. Read tasks FROM the actual Excel files at startup

Archer hardcodes all tasks in Python. I read them from the spreadsheets in `documents/` using openpyxl at startup, with a hardcoded fallback if the files aren't found.

**Why:** Uses real data. If the spreadsheets change, the app picks it up automatically. No manual sync required.

### 3. Named workflow instances with persistence

Each time you start a workflow, you enter the employee name (e.g., "John Smith - Onboarding"). That instance is saved to PocketBase. Progress survives restarts. Multiple concurrent workflows possible.

**Why:** The demo moment is more powerful — "I can show you the Cassie Johnson offboarding from last month." Audit trail means something.

### 4. In-place task completion (no page reload)

Archer does `location.reload()` on task complete. I update the task card in-place via fetch — progress bar animates, card fades to green, no reload.

**Why:** A page reload on a Pi taking 2-3 seconds looks broken in a demo. Smooth is fast.

### 5. Department filter toggle

One button per department (HR, IT, Payroll, Management, Finance). Click IT — see only IT's 8 tasks.

**Why:** Demo moment: "The IT manager only sees their tasks. HR sees everything."

---

## Implementation

See `hr_admin.py` in this folder. It is fully runnable code, not pseudocode.

### Install on Pi

```bash
# Install openpyxl to read Excel files
pip install openpyxl --break-system-packages

# Copy to Pi
scp ~/GoldenImage_Files/hermes/hr_admin.py pi@192.168.68.58:~/GoldenImage_Files/hermes/hr_admin.py
scp ~/GoldenImage_Files/systemd/hr-admin.service pi@192.168.68.58:~/GoldenImage_Files/systemd/hr-admin.service

# Install service on Pi
sudo cp ~/GoldenImage_Files/systemd/hr-admin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable hr-admin
sudo systemctl start hr-admin

# Confirm running
sudo journalctl -u hr-admin -f
```

### Access
- HR Admin Portal: `http://192.168.68.58:5001`
- Demo password: `iliad2026` (set via --password arg or HR_ADMIN_PASSWORD env var)

---

## Consensus Points for Archer

1. **Separate port (5001) vs modifying rest_api_wrapper.py?** I say separate. Cleaner, safer for demo day.
2. **Read from Excel vs hardcode?** I say read from Excel. More resilient, uses real data.
3. **Named instances vs single shared workflow state?** I say named. Better audit story.
4. **In-place completion vs page reload?** I say in-place. Smoother demo.
5. **Department filter?** Nice to have but skippable if time is tight.

Both approaches will work for Tuesday. Mine requires `pip install openpyxl` on the Pi (30 seconds). That's the only additional dependency.

---

---

## Notes for Archer

The consensus questions are now moot — all shipped. If you want to build on top of this, the cleanest next additions are:

- **Email notifications** on task completion (use PocketBase webhooks or a simple SMTP call)
- **PDF export** of completed workflow with timestamps (full audit report for HR files)
- **Multi-user logins** instead of shared password (PocketBase users collection)
- **Archive completed workflows** so the list doesn't grow forever

The fallback task lists in `_FALLBACK_ONBOARDING` and `_FALLBACK_OFFBOARDING` are now the real Iliad data — 70 and 30 tasks respectively. The Excel reader is also fixed to handle their specific spreadsheet structure (col A = task, col E = owner, section headers = rows where col E is empty, data starts row 9 of "Checklist" sheet).

---

**Claude**
April 6, 2026 — 10 PM MT (Darrell's been at it 10 hours, demo is tomorrow at 2 PM MT, and it's ready)
