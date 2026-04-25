#!/usr/bin/env python3
"""
install_watchdog_pi.py — Wires memory_watchdog.py into systemd
==============================================================
For Raspberry Pi and Orange Pi (any Linux with systemd).
Run as the 'pi' user (NOT root — this installs a user-level system service via sudo).

What it does:
  1. Copies memory_watchdog.py to ~/.hermes/memory_watchdog.py
  2. Detects the correct Python (venv first, then system)
  3. Writes a systemd service to /etc/systemd/system/hermes-watchdog.service
  4. Enables and starts the service immediately
  5. Verifies it's running

After this, the watchdog starts automatically on every boot.
No login required — it runs at the system level.
Archer cannot disable it.

Usage (on the Pi, via SSH or terminal):
  python3 install_watchdog_pi.py

To uninstall:
  sudo systemctl stop hermes-watchdog
  sudo systemctl disable hermes-watchdog
  sudo rm /etc/systemd/system/hermes-watchdog.service
  sudo systemctl daemon-reload
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR      = Path(__file__).parent.resolve()
SOURCE_WATCHDOG = SCRIPT_DIR / "memory_watchdog.py"
HOME            = Path.home()
HERMES_DIR      = HOME / ".hermes"
DEST_WATCHDOG   = HERMES_DIR / "memory_watchdog.py"
LOG_FILE        = HERMES_DIR / "watchdog.log"
SERVICE_NAME    = "hermes-watchdog"
SERVICE_PATH    = Path(f"/etc/systemd/system/{SERVICE_NAME}.service")

# Venv Python takes priority (golden image has one at ~/venv)
VENV_PYTHON     = HOME / "venv" / "bin" / "python3"

# ── Helpers ────────────────────────────────────────────────────────────────────

def ok(msg):   print(f"  ✓  {msg}")
def err(msg):  print(f"  ✗  {msg}"); sys.exit(1)
def info(msg): print(f"     {msg}")

def run(cmd, check=True, capture=True):
    return subprocess.run(
        cmd, shell=True, check=check,
        capture_output=capture, text=True
    )

# ── Steps ──────────────────────────────────────────────────────────────────────

def check_source():
    if not SOURCE_WATCHDOG.exists():
        err(f"memory_watchdog.py not found at {SOURCE_WATCHDOG}\n"
            f"     Make sure both files are in the same folder.")
    ok("Found memory_watchdog.py")

def check_systemd():
    result = run("systemctl --version", check=False)
    if result.returncode != 0:
        err("systemd not found. This script requires a systemd-based Linux distro.")
    ok("systemd available")

def check_sudo():
    result = run("sudo -n true", check=False)
    if result.returncode != 0:
        # Prompt for password now rather than mid-install
        print("\n     sudo access is required to install the system service.")
        print("     You may be prompted for your password.\n")
        result2 = run("sudo true", check=False, capture=False)
        if result2.returncode != 0:
            err("sudo access required. Run as a user with sudo privileges.")
    ok("sudo access confirmed")

def find_python() -> str:
    if VENV_PYTHON.exists():
        ok(f"Using venv Python: {VENV_PYTHON}")
        return str(VENV_PYTHON)
    fallback = shutil.which("python3")
    if fallback:
        ok(f"Using system Python: {fallback}")
        return fallback
    err("No python3 found. Install Python 3 or activate the venv first.")

def ensure_hermes_dir():
    HERMES_DIR.mkdir(parents=True, exist_ok=True)
    ok(f"~/.hermes/ exists")

def copy_watchdog():
    shutil.copy2(SOURCE_WATCHDOG, DEST_WATCHDOG)
    DEST_WATCHDOG.chmod(0o755)
    ok(f"Copied to {DEST_WATCHDOG}")

def write_service(python_exe: str):
    current_user = os.environ.get("USER") or os.environ.get("LOGNAME") or "pi"
    service_content = f"""[Unit]
Description=Hermes Memory Watchdog
Documentation=https://github.com/caltongroup/agent-in-a-box
After=network.target pocketbase.service
# Start even if PocketBase isn't a managed service
StartLimitIntervalSec=0

[Service]
Type=simple
User={current_user}
ExecStart={python_exe} {DEST_WATCHDOG}
Restart=always
RestartSec=10
StandardOutput=append:{LOG_FILE}
StandardError=append:{LOG_FILE}

# Give it a moment after boot before first poll
ExecStartPre=/bin/sleep 5

[Install]
WantedBy=multi-user.target
"""
    # Write via sudo since /etc/systemd/system/ requires root
    write_cmd = f"sudo tee {SERVICE_PATH} > /dev/null"
    result = subprocess.run(
        write_cmd, shell=True, input=service_content,
        capture_output=True, text=True
    )
    if result.returncode != 0:
        err(f"Failed to write service file: {result.stderr.strip()}")
    ok(f"Service file written to {SERVICE_PATH}")

def enable_and_start():
    result = run("sudo systemctl daemon-reload", check=False)
    if result.returncode != 0:
        err(f"daemon-reload failed: {result.stderr.strip()}")
    ok("systemd daemon reloaded")

    result = run(f"sudo systemctl enable {SERVICE_NAME}", check=False)
    if result.returncode != 0:
        err(f"Enable failed: {result.stderr.strip()}")
    ok(f"Service enabled (will start on every boot)")

    result = run(f"sudo systemctl start {SERVICE_NAME}", check=False)
    if result.returncode != 0:
        err(f"Start failed: {result.stderr.strip()}")
    ok("Service started")

def verify_running():
    import time
    time.sleep(2)  # Give systemd a moment to settle
    result = run(f"sudo systemctl is-active {SERVICE_NAME}", check=False)
    status = result.stdout.strip()
    if status == "active":
        ok("Watchdog is RUNNING (active)")
    else:
        info(f"Service status: {status}")
        info(f"Check logs: sudo journalctl -u {SERVICE_NAME} -n 20")
        info(f"Or: tail -f {LOG_FILE}")

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("\n=== Hermes Memory Watchdog Installer (Pi/Linux) ===\n")

    check_source()
    check_systemd()
    check_sudo()
    python_exe = find_python()
    ensure_hermes_dir()
    copy_watchdog()
    write_service(python_exe)
    enable_and_start()
    verify_running()

    print(f"""
=== Installation complete ===

The watchdog is now running independently of the agent.
It polls every 60 seconds and forces a memory dump when:
  - 8+ new interactions have occurred since the last dump, OR
  - The session context file exceeds 1,700 characters

The agent cannot disable or bypass this. It starts automatically on every boot.

Useful commands:
  Check status:   sudo systemctl status {SERVICE_NAME}
  View log:       tail -f {LOG_FILE}
  Live log:       sudo journalctl -u {SERVICE_NAME} -f
  Stop watchdog:  sudo systemctl stop {SERVICE_NAME}
  Start watchdog: sudo systemctl start {SERVICE_NAME}
""")

if __name__ == "__main__":
    main()
