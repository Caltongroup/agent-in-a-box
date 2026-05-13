#!/usr/bin/env python3
# =============================================================================
# onboard_wizard.py — Penelope: Agent in a Box  |  First-Boot Setup Wizard
# Decision ID: d3a11098-1cf6-444f-8293-7462a6e9e3cc
# Runs as `pi` on first boot/SSH. Fully idempotent. 100% generic.
# Prerequisites on golden image: venv, PocketBase, Ollama, Phi-3.5-mini,
# nomic-embed-text, Hermes skeleton.
#
# "Penelope" is the product brand. Each deployment gives her a name and a home.
# =============================================================================

import os, sys, time, subprocess
from pathlib import Path

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
HOME       = Path("/home/pi")
VENV       = HOME / "venv"
PB_BIN     = HOME / "pocketbase" / "pocketbase"
PB_DATA    = HOME / "pocketbase" / "data"
PB_URL     = "http://127.0.0.1:8090"
HERMES     = HOME / "hermes"
DONE_FLAG  = HOME / ".agent_wizard_complete"
MODEL      = "qwen2.5:1.5b"
EMBED      = "nomic-embed-text"

# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------
def ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    try:
        v = input(f"  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print(); sys.exit(0)
    return v or default

def banner(t): print(f"\n{'='*60}\n  {t}\n{'='*60}")
def ok(t):     print(f"  ✓  {t}")
def info(t):   print(f"  →  {t}")
def warn(t):   print(f"  ⚠  {t}", file=sys.stderr)

# ---------------------------------------------------------------------------
# 1. Questionnaire
# ---------------------------------------------------------------------------
def questionnaire():
    banner("Penelope — Agent in a Box  |  First-Boot Setup")
    print("  Meet Penelope: your local AI agent, ready for any vertical.")
    print("  Press Enter to accept defaults shown in [brackets].\n")

    cfg = {
        "agent_name":    ask("Agent name (this is what people will call her)", "Penelope"),
        "business_name": ask("Business / Organization Name", "My Organization"),
        "vertical":      ask("Industry / Vertical (e.g. HR, Radio Station, Senior Care, Retail)", "General"),
        "purpose":       ask("Main purpose of this agent (one sentence)",
                             "Assist staff and customers with information and task support"),
        "contacts":      [],
    }

    print("\n  Key Contacts — type 'done' at any prompt to finish.")
    print("  Tip: add a Telegram chat ID to restrict bot access to that person.\n")
    while True:
        name = ask("  Contact name ('done' to stop)", "")
        if not name or name.lower() == "done": break
        email = ask("  Contact email", "")
        if email.lower() == "done": break
        role = ask("  Contact role", "Staff")
        if role.lower() == "done": break
        tg_id = ask("  Telegram chat ID (optional — leave blank to skip)", "")
        cfg["contacts"].append({
            "name": name, "email": email, "role": role,
            "telegram_chat_id": tg_id,
        })
        print()
    return cfg

# ---------------------------------------------------------------------------
# 2 & 6. Project folder + RAG structure
# ---------------------------------------------------------------------------
def make_project_folder(name):
    slug = name.lower().replace(" ", "_")
    folder = HOME / f"{slug}_agent"
    for sub in ["", "documents", "chroma_db"]:
        (folder / sub).mkdir(parents=True, exist_ok=True)
    ok(f"Project folder: {folder}")
    return folder

# ---------------------------------------------------------------------------
# 3. SOUL.md
# ---------------------------------------------------------------------------
def write_soul(folder, cfg):
    slug = cfg["business_name"].lower().replace(" ", "_")
    agent_name = cfg["agent_name"]
    contact_lines = "\n".join(
        f"- {c['name']} ({c['role']}) — {c['email']}" for c in cfg["contacts"]
    ) or "- (none provided)"
    soul = f"""# SOUL.md — {agent_name} for {cfg['business_name']}
# Powered by Penelope: Agent in a Box
# Edit this file anytime to adjust personality, rules, or contacts.

## Identity
- **Name:** {agent_name}
- **Business:** {cfg['business_name']}
- **Vertical:** {cfg['vertical']}
- **Purpose:** {cfg['purpose']}

## Personality
Your name is {agent_name}. You are a friendly, professional AI assistant
representing {cfg['business_name']} in the {cfg['vertical']} sector.
Your tone is warm, clear, and concise. You are knowledgeable but never arrogant.
You make people feel heard and well-supported.

## Rules
1. Keep replies short unless more detail is explicitly requested.
2. Escalate legal, medical, financial, or safety questions to a human immediately.
3. Always cite the source when referencing documents or data.
4. Stay in scope — politely redirect off-topic requests.
5. Never share personal or confidential information unnecessarily.
6. When uncertain, say so — never guess and present it as fact.

## Key Contacts
{contact_lines}

## Technical (do not edit)
- Engine: Penelope v1 | Model: Phi-3.5-mini ({MODEL})
- Embeddings: {EMBED} | Vector store: ChromaDB (`{slug}`)
- Memory / sessions: PocketBase
"""
    path = folder / "SOUL.md"
    path.write_text(soul)
    ok(f"SOUL.md: {path}")

# ---------------------------------------------------------------------------
# 4 & 5. PocketBase collections + seed contacts
# ---------------------------------------------------------------------------
def pb_start():
    try:
        if requests.get(f"{PB_URL}/api/health", timeout=2).status_code == 200:
            ok("PocketBase already running"); return
    except requests.ConnectionError:
        pass
    info("Starting PocketBase…")
    subprocess.Popen([str(PB_BIN), "serve", "--dir", str(PB_DATA)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(15):
        time.sleep(1)
        try:
            if requests.get(f"{PB_URL}/api/health", timeout=2).status_code == 200:
                ok("PocketBase started"); return
        except requests.ConnectionError:
            pass
    warn("PocketBase did not start — collections will be skipped")

def pb_ensure_collection(name, fields):
    try:
        if requests.get(f"{PB_URL}/api/collections/{name}", timeout=5).status_code == 200:
            ok(f"Collection exists: {name}"); return
        r = requests.post(f"{PB_URL}/api/collections",
                          json={"name": name, "type": "base", "schema": fields}, timeout=5)
        ok(f"Collection created: {name}") if r.status_code in (200, 201) \
            else warn(f"Could not create '{name}': {r.text[:80]}")
    except requests.ConnectionError:
        warn(f"PocketBase unreachable — skipped '{name}'")

def ensure_collections(vertical):
    prefix = "hr_" if "hr" in vertical.lower() else ""
    defs = {
        "sessions":    [{"name": "summary",  "type": "text",  "required": False},
                        {"name": "chat_id",  "type": "text",  "required": False},
                        {"name": "type",     "type": "text",  "required": False}],
        "escalations": [{"name": "reason",   "type": "text",  "required": False}],
        "documents":   [{"name": "filename", "type": "text",  "required": False}],
        "contacts":    [{"name": "name",              "type": "text",  "required": True},
                        {"name": "email",             "type": "email", "required": False},
                        {"name": "role",              "type": "text",  "required": False},
                        {"name": "telegram_chat_id",  "type": "text",  "required": False}],
    }
    col_map = {}
    for base, fields in defs.items():
        col = f"{prefix}{base}"
        pb_ensure_collection(col, fields)
        col_map[base] = col
    return col_map

# [3] PocketBase admin password — must be set before wizard completes
def pb_setup_admin():
    """Create PocketBase admin account if none exists. Blocks until set."""
    # Check if admin already exists by attempting unauthenticated admin list
    try:
        r = requests.get(f"{PB_URL}/api/admins", timeout=5)
        if r.status_code == 401:
            ok("PocketBase admin already configured")
            return   # 401 = auth required = admin exists
    except requests.ConnectionError:
        warn("PocketBase unreachable — skipping admin setup")
        return

    print("\n  ── PocketBase Admin Setup ──")
    print("  Set a strong password — this protects all your agent data.\n")
    while True:
        email    = ask("  Admin email", "admin@localhost")
        password = ask("  Admin password (min 10 characters)", "")
        if len(password) < 10:
            print("  ⚠  Password must be at least 10 characters. Try again.\n")
            continue
        confirm  = ask("  Confirm password", "")
        if password != confirm:
            print("  ⚠  Passwords do not match. Try again.\n")
            continue
        try:
            r = requests.post(f"{PB_URL}/api/admins", json={
                "email":           email,
                "password":        password,
                "passwordConfirm": confirm,
            }, timeout=5)
            if r.status_code in (200, 201):
                ok(f"PocketBase admin created: {email}")
                ok("Dashboard: http://<your-pi-ip>:8090/_/")
                return
            else:
                warn(f"Admin setup failed: {r.text[:100]}")
        except requests.ConnectionError:
            warn("PocketBase unreachable — skipping admin setup")
            return

def seed_contacts(col, contacts):
    for c in contacts:
        try:
            r = requests.post(f"{PB_URL}/api/collections/{col}/records", json=c, timeout=5)
            if r.status_code in (200, 201):        ok(f"Seeded: {c['name']}")
            elif "unique" in r.text.lower():       ok(f"Already exists: {c['name']}")
            else:                                  warn(f"Seed failed {c['name']}: {r.text[:80]}")
        except requests.ConnectionError:
            warn("PocketBase unreachable — contact seed aborted"); break

# ---------------------------------------------------------------------------
# 7. start_agent.sh
# ---------------------------------------------------------------------------
def write_start_script(folder, cfg, col_map):
    slug = cfg["business_name"].lower().replace(" ", "_")
    agent_name = cfg["agent_name"]
    script = f"""#!/usr/bin/env bash
# start_agent.sh — {agent_name} for {cfg['business_name']}
# Powered by Penelope: Agent in a Box
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

source "{VENV}/bin/activate"

# 1. Start PocketBase if not running
if ! curl -sf {PB_URL}/api/health >/dev/null 2>&1; then
    echo "[*] Starting PocketBase…"
    nohup "{PB_BIN}" serve --dir "{PB_DATA}" >/tmp/pocketbase.log 2>&1 &
    sleep 3
fi

# 2. Run initial document ingestion (idempotent — skips already-indexed files)
echo "[*] Indexing documents…"
python "$SCRIPT_DIR/ingest.py" \\
    --docs       "{folder}/documents" \\
    --collection "{slug}"             \\
    --chroma-dir "{folder}/chroma_db"

# 3. Start document watcher in background (auto-ingests new files)
echo "[*] Starting document watcher…"
nohup python "$SCRIPT_DIR/watcher.py" \\
    --docs       "{folder}/documents" \\
    --collection "{slug}"             \\
    --chroma-dir "{folder}/chroma_db" \\
    --interval   30 >/tmp/watcher.log 2>&1 &

# 4. Launch the Hermes agent
echo "[*] Launching {agent_name} for {cfg['business_name']}…"
python "{HERMES}/main.py" \\
    --model       "{MODEL}"                   \\
    --embed-model "{EMBED}"                   \\
    --soul        "{folder}/SOUL.md"          \\
    --docs        "{folder}/documents"        \\
    --chroma-dir  "{folder}/chroma_db"        \\
    --collection  "{slug}"                    \\
    --pb-url      "{PB_URL}"                  \\
    --pb-contacts "{col_map.get('contacts','contacts')}"
"""
    p = folder / "start_agent.sh"
    p.write_text(script)
    p.chmod(0o755)
    ok(f"start_agent.sh: {p}")

# ---------------------------------------------------------------------------
# 8. Next steps
# ---------------------------------------------------------------------------
def print_next_steps(folder, cfg):
    agent_name = cfg["agent_name"]
    banner(f"{agent_name} is ready — Next Steps")
    print(f"""
  1. Drop your documents into:
       {folder}/documents/

  2. Start {agent_name}:
       bash {folder}/start_agent.sh

  3. Adjust {agent_name}'s personality anytime by editing:
       {folder}/SOUL.md

  4. Manage memory and contacts in PocketBase:
       http://<your-pi-ip>:8090/_/

  5. Re-run this wizard to change settings (fully idempotent):
       python3 ~/onboard_wizard.py
       (delete ~/.agent_wizard_complete first to reset)

  Penelope: Agent in a Box  |  Built on Phi-3.5-mini + nomic-embed-text
""")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if DONE_FLAG.exists():
        print(f"\n  Wizard already completed ({DONE_FLAG.read_text().strip()}).")
        print("  Delete ~/.agent_wizard_complete to re-run.\n")
        return
    cfg    = questionnaire()
    banner(f"Setting up {cfg['agent_name']} for {cfg['business_name']}…")
    folder = make_project_folder(cfg["business_name"])
    write_soul(folder, cfg)
    pb_start()
    pb_setup_admin()
    col_map = ensure_collections(cfg["vertical"])
    seed_contacts(col_map["contacts"], cfg["contacts"])
    write_start_script(folder, cfg, col_map)
    DONE_FLAG.write_text(
        f"{cfg['agent_name']} configured for {cfg['business_name']} "
        f"on {__import__('datetime').date.today()}"
    )
    print_next_steps(folder, cfg)

if __name__ == "__main__":
    main()
