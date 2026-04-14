#!/usr/bin/env python3
# =============================================================================
# onboard_wizard.py — Agent in a Box: First-Boot Configurator
# Runs as the pi user on first boot or first SSH.
# Idempotent: safe to run multiple times.
# Usage: python3 onboard_wizard.py
# =============================================================================

import os
import sys
import json
import subprocess
import textwrap
from pathlib import Path
from datetime import datetime

# ── Helpers ───────────────────────────────────────────────────────────────────

CYAN  = "\033[0;36m"
GREEN = "\033[0;32m"
YELLOW= "\033[1;33m"
NC    = "\033[0m"

def banner(msg):
    print(f"\n{CYAN}{'═'*50}{NC}")
    print(f"{CYAN}  {msg}{NC}")
    print(f"{CYAN}{'═'*50}{NC}\n")

def ok(msg):   print(f"{GREEN}✓ {msg}{NC}")
def info(msg): print(f"{CYAN}→ {msg}{NC}")
def warn(msg): print(f"{YELLOW}⚠ {msg}{NC}")

def ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{CYAN}{prompt}{suffix}: {NC}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        val = ""
    return val if val else default

def slug(text):
    return text.lower().replace(" ", "_").replace("-", "_")

# ── PocketBase ────────────────────────────────────────────────────────────────

PB_URL = "http://127.0.0.1:8090"

def pb_admin_token():
    """Get PocketBase superuser token. Returns token or None."""
    import urllib.request, urllib.error
    creds_file = Path.home() / ".pb_admin_creds"
    if not creds_file.exists():
        return None
    creds = json.loads(creds_file.read_text())
    payload = json.dumps({
        "identity": creds["email"],
        "password": creds["password"]
    }).encode()
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/_superusers/auth-with-password",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())["token"]
    except Exception:
        return None

def pb_ensure_collection(token, name, fields):
    """Create PocketBase collection if it doesn't already exist."""
    import urllib.request, urllib.error
    headers = {"Content-Type": "application/json", "Authorization": token}

    # Check if exists
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/{name}",
        headers=headers
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        ok(f"Collection already exists: {name}")
        return
    except urllib.error.HTTPError as e:
        if e.code != 404:
            warn(f"Could not check collection {name}: {e}")
            return

    # Create it
    payload = json.dumps({
        "name": name,
        "type": "base",
        "fields": fields
    }).encode()
    req = urllib.request.Request(
        f"{PB_URL}/api/collections",
        data=payload,
        headers=headers,
        method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        ok(f"Created collection: {name}")
    except Exception as e:
        warn(f"Could not create collection {name}: {e}")

def pb_insert(token, collection, record):
    """Insert a record into a PocketBase collection."""
    import urllib.request
    headers = {"Content-Type": "application/json", "Authorization": token}
    payload = json.dumps(record).encode()
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/{collection}/records",
        data=payload,
        headers=headers,
        method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False

# ── SOUL.md generator ─────────────────────────────────────────────────────────

def personality_for_vertical(vertical):
    v = vertical.lower()
    if any(x in v for x in ["hr", "human resource"]):
        return ("Warm, professional, and discreet. Speaks clearly and avoids jargon. "
                "Maintains strict confidentiality and always refers sensitive matters "
                "to the appropriate human.")
    if any(x in v for x in ["radio", "broadcast", "station"]):
        return ("Upbeat, creative, and quick. Understands music, scheduling, and "
                "audience engagement. Communicates with energy while staying organised.")
    if any(x in v for x in ["senior", "care", "health", "medical"]):
        return ("Gentle, patient, and clear. Uses simple language, never rushes, "
                "and always escalates health or safety concerns immediately to a human.")
    if any(x in v for x in ["retail", "sales", "shop"]):
        return ("Friendly, helpful, and efficient. Focuses on solving customer problems "
                "quickly and knows when to involve a human team member.")
    if any(x in v for x in ["legal", "law"]):
        return ("Precise, measured, and careful. Never offers legal advice. "
                "Summarises clearly and always defers final decisions to qualified staff.")
    # Generic default
    return ("Professional, helpful, and concise. Adapts tone to the task at hand. "
            "Always transparent about being an AI and escalates sensitive matters "
            "to the appropriate human contact.")

def generate_soul(business, vertical, purpose, contacts):
    personality = personality_for_vertical(vertical)
    contact_block = ""
    if contacts:
        contact_block = "\n## Key Contacts\n"
        for c in contacts:
            contact_block += f"- **{c['name']}** ({c['role']}) — {c['email']}\n"

    return textwrap.dedent(f"""\
        # SOUL.md — {business}
        *Generated by Agent in a Box on {datetime.now().strftime('%Y-%m-%d %H:%M')}*

        ## Identity
        - **Organisation:** {business}
        - **Industry / Vertical:** {vertical}
        - **Purpose:** {purpose}

        ## Personality
        {personality}

        ## Core Rules
        1. Keep replies short and clear unless the user asks for detail.
        2. Always cite sources when providing facts or recommendations.
        3. Escalate sensitive, legal, financial, or safety topics to a human immediately.
        4. Never pretend to be human — always be transparent that you are an AI agent.
        5. If unsure, say so and ask for clarification rather than guessing.
        6. Respect confidentiality — do not share information outside its intended audience.
        {contact_block}
        ## Model Stack
        - **Primary:** Phi-3.5-mini (local, Ollama)
        - **Embeddings:** nomic-embed-text (local, Ollama)
        - **RAG store:** ChromaDB (local)
        - **Memory backend:** PocketBase (local)
    """)

# ── start_agent.sh generator ──────────────────────────────────────────────────

def generate_start_script(project_dir, business_slug):
    data_dir = Path("/home/pi/data")
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # start_agent.sh — Launch agent for {business_slug}
        set -euo pipefail

        PROJECT_DIR="{project_dir}"
        VENV="{data_dir}/venv"
        PB_DIR="{data_dir}/pocketbase"
        PB_BIN="$PB_DIR/pocketbase"

        # Activate venv
        source "$VENV/bin/activate"

        # Start PocketBase if not running
        if ! pgrep -f "pocketbase serve" > /dev/null; then
            echo "Starting PocketBase..."
            nohup "$PB_BIN" serve --http=0.0.0.0:8090 > "$PB_DIR/pb.log" 2>&1 &
            sleep 2
        fi

        # Start Ollama if not running
        if ! pgrep -f "ollama serve" > /dev/null; then
            echo "Starting Ollama..."
            nohup ollama serve > /tmp/ollama.log 2>&1 &
            sleep 2
        fi

        # Launch agent
        echo "Launching agent: {business_slug}"
        cd "$PROJECT_DIR"
        python3 "{data_dir}/hermes/agent.py" \\
            --soul "$PROJECT_DIR/SOUL.md" \\
            --rag  "$PROJECT_DIR/chroma_db" \\
            --docs "$PROJECT_DIR/documents" \\
            --model phi3.5
    """)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    banner("Agent in a Box — Onboarding Wizard")
    print("Answer the questions below to configure this agent.")
    print("Press Enter to accept the default shown in [brackets].\n")

    # ── Questionnaire ─────────────────────────────────────────────────────────
    business  = ask("Business / Organisation name", "My Organisation")
    vertical  = ask("Industry / Vertical (e.g. HR, Radio Station, Senior Care, Retail)", "General")
    purpose   = ask("Main purpose of this agent (one sentence)",
                    "Help staff find information and automate routine tasks")

    # Contacts loop
    contacts = []
    print(f"\n{CYAN}Key contacts — type 'done' when finished{NC}")
    while True:
        name = ask("  Contact name (or 'done')", "done")
        if name.lower() == "done":
            break
        email = ask("  Email")
        role  = ask("  Role")
        contacts.append({"name": name, "email": email, "role": role})
        ok(f"Added: {name}")

    # ── Project folder ────────────────────────────────────────────────────────
    business_slug = slug(business)
    project_dir   = Path(f"/home/pi/data/agents/{business_slug}_agent")
    project_dir.mkdir(parents=True, exist_ok=True)
    ok(f"Project folder: {project_dir}")

    # ── SOUL.md ───────────────────────────────────────────────────────────────
    soul_path = project_dir / "SOUL.md"
    soul_content = generate_soul(business, vertical, purpose, contacts)
    soul_path.write_text(soul_content)
    ok(f"SOUL.md written: {soul_path}")

    # ── RAG folder structure ──────────────────────────────────────────────────
    (project_dir / "documents").mkdir(exist_ok=True)
    (project_dir / "chroma_db").mkdir(exist_ok=True)
    ok("RAG folders ready (documents/, chroma_db/)")

    # ── start_agent.sh ────────────────────────────────────────────────────────
    start_script = project_dir / "start_agent.sh"
    start_script.write_text(generate_start_script(project_dir, business_slug))
    start_script.chmod(0o755)
    ok(f"start_agent.sh written: {start_script}")

    # ── PocketBase collections ────────────────────────────────────────────────
    info("Setting up PocketBase collections...")
    token = pb_admin_token()
    if token:
        v = vertical.lower()
        prefix = ""
        if "hr" in v or "human resource" in v:
            prefix = "hr_"
        elif "radio" in v or "broadcast" in v:
            prefix = "radio_"

        text_field  = [{"name": "content",    "type": "text",  "required": False}]
        basic_field = [{"name": "summary",    "type": "text",  "required": False}]
        contact_fields = [
            {"name": "name",  "type": "text",  "required": True},
            {"name": "email", "type": "email", "required": False},
            {"name": "role",  "type": "text",  "required": False},
        ]

        pb_ensure_collection(token, f"{prefix}sessions",    text_field)
        pb_ensure_collection(token, f"{prefix}escalations", basic_field)
        pb_ensure_collection(token, f"{prefix}documents",   text_field)
        pb_ensure_collection(token, "contacts",             contact_fields)

        # Seed contacts
        for c in contacts:
            if pb_insert(token, "contacts", c):
                ok(f"Seeded contact: {c['name']}")
            else:
                warn(f"Could not seed contact: {c['name']} (may already exist)")
    else:
        warn("PocketBase not reachable or no credentials found — skipping collections.")
        warn("Create ~/.pb_admin_creds with {\"email\":\"...\",\"password\":\"...\"} and re-run.")

    # ── Next steps ────────────────────────────────────────────────────────────
    banner("Setup complete!")
    print(f"  Project folder : {project_dir}")
    print(f"  SOUL.md        : {soul_path}")
    print(f"  PocketBase     : http://$(hostname -I | awk '{{print $1}}'):8090/_\n")
    print(f"{YELLOW}Next steps:{NC}")
    print(f"  1. Drop documents into:  {project_dir}/documents/")
    print(f"  2. Start your agent:     bash {start_script}")
    print(f"  3. Open PocketBase UI:   http://<pi-ip>:8090/_")
    print()

if __name__ == "__main__":
    main()
