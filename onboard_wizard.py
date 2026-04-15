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
import socket
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

def run(cmd, check=True, capture=False):
    """Run a shell command. Returns CompletedProcess."""
    return subprocess.run(
        cmd, shell=True, check=check,
        capture_output=capture, text=True
    )

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
    return ("Professional, helpful, and concise. Adapts tone to the task at hand. "
            "Always transparent about being an AI and escalates sensitive matters "
            "to the appropriate human contact.")

def generate_soul(business, vertical, purpose, contacts):
    personality = personality_for_vertical(vertical)
    lines = [
        f"# SOUL.md — {business}",
        f"*Generated by Agent in a Box on {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "## Identity",
        f"- **Organisation:** {business}",
        f"- **Industry / Vertical:** {vertical}",
        f"- **Purpose:** {purpose}",
        "",
        "## Personality",
        personality,
        "",
        "## Core Rules",
        "1. Keep replies short and clear unless the user asks for detail.",
        "2. Always cite sources when providing facts or recommendations.",
        "3. Escalate sensitive, legal, financial, or safety topics to a human immediately.",
        "4. Never pretend to be human — always be transparent that you are an AI agent.",
        "5. If unsure, say so and ask for clarification rather than guessing.",
        "6. Respect confidentiality — do not share information outside its intended audience.",
    ]
    if contacts:
        lines += ["", "## Key Contacts"]
        for c in contacts:
            lines.append(f"- **{c['name']}** ({c['role']}) — {c['email']}")
    lines += [
        "",
        "## Model Stack",
        "- **Inference:** qwen2.5:1.5b via llama-server (local, port 8080)",
        "- **Embeddings:** nomic-embed-text via Ollama (local)",
        "- **RAG store:** ChromaDB (local)",
        "- **Memory backend:** PocketBase (local, port 8090)",
        "",
    ]
    return "\n".join(lines)

# ── Systemd service writers ───────────────────────────────────────────────────

def write_web_ui_service(service_name, agent_name, soul_path,
                          chroma_db, collection, port, data_dir):
    """Create (or update) a systemd service for the web UI."""
    service_path = Path(f"/etc/systemd/system/{service_name}.service")
    venv_python = f"{data_dir}/venv/bin/python3"
    web_ui = f"{data_dir}/web_ui.py"

    content = textwrap.dedent(f"""\
        [Unit]
        Description=Agent in a Box — {agent_name}
        After=network.target llama-server.service

        [Service]
        Type=simple
        User=pi
        WorkingDirectory={data_dir}
        ExecStart={venv_python} {web_ui} \\
            --soul {soul_path} \\
            --chroma-db {chroma_db} \\
            --collection {collection} \\
            --agent-name "{agent_name}" \\
            --port {port}
        Restart=always
        RestartSec=5
        Environment=PYTHONUNBUFFERED=1

        [Install]
        WantedBy=multi-user.target
    """)

    try:
        service_path.write_text(content)
        run("systemctl daemon-reload")
        run(f"systemctl enable {service_name}")
        ok(f"Service created and enabled: {service_name}")
        return True
    except PermissionError:
        warn("Not running as root — skipping systemd service creation.")
        warn(f"Re-run with sudo to install the service, or copy manually to /etc/systemd/system/")
        # Write to project dir so user can install it themselves
        return False

def start_service(service_name):
    """Start a systemd service, warn if it fails."""
    result = run(f"systemctl start {service_name}", check=False)
    if result.returncode == 0:
        ok(f"Service started: {service_name}")
    else:
        warn(f"Could not start {service_name} — check: sudo systemctl status {service_name}")

# ── Document repo cloning ─────────────────────────────────────────────────────

def clone_or_pull_repo(repo_url, dest_dir):
    """Clone repo if not present; pull if it is. Returns True on success."""
    dest = Path(dest_dir)
    if (dest / ".git").exists():
        info(f"Updating documents repo in {dest}...")
        result = run(f"git -C {dest} pull --quiet", check=False)
        if result.returncode == 0:
            ok("Documents repo up to date")
        else:
            warn("git pull failed — using existing documents")
        return True
    else:
        info(f"Cloning documents repo → {dest}...")
        result = run(f"git clone --quiet {repo_url} {dest}", check=False)
        if result.returncode == 0:
            ok(f"Documents cloned from {repo_url}")
            return True
        else:
            warn(f"Could not clone {repo_url} — you can add documents manually to {dest}")
            return False

def run_ingest(data_dir, chroma_db, collection, docs_dir):
    """Run ingest.py to build the ChromaDB vector store."""
    venv_python = f"{data_dir}/venv/bin/python3"
    ingest_script = f"{data_dir}/ingest.py"
    if not Path(ingest_script).exists():
        warn(f"ingest.py not found at {ingest_script} — skipping RAG build")
        return
    info("Building RAG vector store (this may take a minute)...")
    result = run(
        f"{venv_python} {ingest_script} "
        f"--chroma-db {chroma_db} "
        f"--collection {collection} "
        f"--docs {docs_dir}",
        check=False
    )
    if result.returncode == 0:
        ok("RAG vector store built")
    else:
        warn("ingest.py returned an error — check documents and try again manually")

# ── start_agent.sh generator ──────────────────────────────────────────────────

def generate_start_script(project_dir, business_slug, service_name, data_dir):
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # start_agent.sh — Launch agent for {business_slug}
        # This script is a manual fallback; the preferred method is:
        #   sudo systemctl start {service_name}
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

        # Start llama-server if not running
        if ! curl -sf http://127.0.0.1:8080/health > /dev/null 2>&1; then
            echo "llama-server not running — try: sudo systemctl start llama-server"
        fi

        # Launch web UI
        echo "Launching agent: {business_slug}"
        exec "$VENV/bin/python3" "{data_dir}/web_ui.py" \\
            --soul "$PROJECT_DIR/SOUL.md" \\
            --chroma-db "$PROJECT_DIR/chroma_db" \\
            --collection "{business_slug}" \\
            --agent-name "{business_slug.replace('_', ' ').title()}" \\
            --port 5000
    """)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    banner("Agent in a Box — Onboarding Wizard")
    print("Answer the questions below to configure this agent.")
    print("Press Enter to accept the default shown in [brackets].\n")

    DATA_DIR = Path("/home/pi/data")

    # ── Questionnaire ─────────────────────────────────────────────────────────
    business  = ask("Business / Organisation name", "My Organisation")
    vertical  = ask("Industry / Vertical (e.g. HR, Radio Station, Senior Care, Retail)", "General")
    purpose   = ask("Main purpose of this agent (one sentence)",
                    "Help staff find information and automate routine tasks")

    # Optional: private GitHub repo for documents
    print(f"\n{CYAN}Document repository (optional){NC}")
    print("If your organisation has a private GitHub repo with documents, enter it here.")
    print("Leave blank to skip — you can drop files into the documents/ folder manually.\n")
    doc_repo = ask("GitHub repo URL (HTTPS, e.g. https://github.com/Org/repo)", "")

    # Web UI port
    port = ask("Web UI port", "5000")

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
    project_dir   = DATA_DIR / "agents" / f"{business_slug}_agent"
    project_dir.mkdir(parents=True, exist_ok=True)
    ok(f"Project folder: {project_dir}")

    # ── SOUL.md ───────────────────────────────────────────────────────────────
    soul_path = project_dir / "SOUL.md"
    soul_path.write_text(generate_soul(business, vertical, purpose, contacts))
    ok(f"SOUL.md written: {soul_path}")

    # ── RAG folder structure ──────────────────────────────────────────────────
    docs_dir   = project_dir / "documents"
    chroma_dir = project_dir / "chroma_db"
    docs_dir.mkdir(exist_ok=True)
    chroma_dir.mkdir(exist_ok=True)
    ok("RAG folders ready (documents/, chroma_db/)")

    # ── Clone document repo ───────────────────────────────────────────────────
    if doc_repo:
        cloned = clone_or_pull_repo(doc_repo, docs_dir)
        if cloned:
            run_ingest(DATA_DIR, chroma_dir, business_slug, docs_dir)
    else:
        info("No document repo specified — add files to documents/ and run ingest.py manually")

    # ── start_agent.sh ────────────────────────────────────────────────────────
    service_name  = f"{business_slug}-agent"
    start_script  = project_dir / "start_agent.sh"
    start_script.write_text(
        generate_start_script(project_dir, business_slug, service_name, DATA_DIR)
    )
    start_script.chmod(0o755)
    ok(f"start_agent.sh written: {start_script}")

    # ── Systemd service ───────────────────────────────────────────────────────
    info("Installing systemd service...")
    service_ok = write_web_ui_service(
        service_name=service_name,
        agent_name=f"{business} Agent",
        soul_path=soul_path,
        chroma_db=chroma_dir,
        collection=business_slug,
        port=port,
        data_dir=DATA_DIR
    )
    if service_ok:
        start_service(service_name)

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

        text_field     = [{"name": "content", "type": "text",  "required": False}]
        basic_field    = [{"name": "summary", "type": "text",  "required": False}]
        contact_fields = [
            {"name": "name",  "type": "text",  "required": True},
            {"name": "email", "type": "email", "required": False},
            {"name": "role",  "type": "text",  "required": False},
        ]

        pb_ensure_collection(token, f"{prefix}sessions",    text_field)
        pb_ensure_collection(token, f"{prefix}escalations", basic_field)
        pb_ensure_collection(token, f"{prefix}documents",   text_field)
        pb_ensure_collection(token, "contacts",             contact_fields)

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
    try:
        pi_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        pi_ip = "<pi-ip>"

    print(f"  Project folder : {project_dir}")
    print(f"  SOUL.md        : {soul_path}")
    print(f"  Web UI service : {service_name}")
    print(f"  Web UI         : http://{pi_ip}:{port}")
    print(f"  PocketBase     : http://{pi_ip}:8090/_\n")
    print(f"{YELLOW}Next steps:{NC}")
    if not doc_repo:
        print(f"  1. Drop documents into : {docs_dir}")
        print(f"     Then run            : source {DATA_DIR}/venv/bin/activate")
        print(f"                           python3 {DATA_DIR}/ingest.py \\")
        print(f"                             --chroma-db {chroma_dir} \\")
        print(f"                             --collection {business_slug} \\")
        print(f"                             --docs {docs_dir}")
    else:
        print(f"  1. Documents ingested from repo — RAG is ready")
    if service_ok:
        print(f"  2. Agent is running    : sudo systemctl status {service_name}")
        print(f"     Restart with        : sudo systemctl restart {service_name}")
    else:
        print(f"  2. Start manually      : bash {start_script}")
        print(f"     Or install service  : sudo bash {start_script}")
    print(f"  3. Open in browser     : http://<pi-ip>:{port}")
    print(f"  4. PocketBase UI       : http://<pi-ip>:8090/_")
    print()

if __name__ == "__main__":
    main()
