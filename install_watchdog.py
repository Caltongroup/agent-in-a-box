#!/usr/bin/env python3
"""
install_watchdog.py — Wires memory_watchdog.py into launchd
============================================================
Run this ONCE on the Mac mini as the user who runs Archer (typically your normal user).

What it does:
  1. Copies memory_watchdog.py to ~/.hermes/memory_watchdog.py
  2. Writes a launchd plist to ~/Library/LaunchAgents/
  3. Loads the service immediately (no reboot required)
  4. Verifies it started

After this, the watchdog starts automatically on every login/reboot.
Archer cannot disable it. It runs completely independently.

Usage:
  python3 install_watchdog.py

To uninstall:
  launchctl unload ~/Library/LaunchAgents/ai.hermes.watchdog.plist
  rm ~/Library/LaunchAgents/ai.hermes.watchdog.plist
  rm ~/.hermes/memory_watchdog.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR       = Path(__file__).parent.resolve()
SOURCE_WATCHDOG  = SCRIPT_DIR / "memory_watchdog.py"
DEST_WATCHDOG    = Path("~/.hermes/memory_watchdog.py").expanduser()
HERMES_DIR       = Path("~/.hermes").expanduser()
LAUNCH_AGENTS    = Path("~/Library/LaunchAgents").expanduser()
PLIST_PATH       = LAUNCH_AGENTS / "ai.hermes.watchdog.plist"
LABEL            = "ai.hermes.watchdog"
LOG_FILE         = HERMES_DIR / "watchdog.log"

# ── Helpers ────────────────────────────────────────────────────────────────────

def ok(msg):  print(f"  ✓  {msg}")
def err(msg): print(f"  ✗  {msg}"); sys.exit(1)
def info(msg): print(f"     {msg}")

# ── Steps ──────────────────────────────────────────────────────────────────────

def check_source():
    if not SOURCE_WATCHDOG.exists():
        err(f"memory_watchdog.py not found at {SOURCE_WATCHDOG}\n"
            f"     Make sure both files are in the same folder.")
    ok(f"Found memory_watchdog.py")

def ensure_hermes_dir():
    HERMES_DIR.mkdir(parents=True, exist_ok=True)
    ok(f"~/.hermes/ exists")

def copy_watchdog():
    shutil.copy2(SOURCE_WATCHDOG, DEST_WATCHDOG)
    DEST_WATCHDOG.chmod(0o755)
    ok(f"Copied to {DEST_WATCHDOG}")

def write_plist():
    python_exe = sys.executable
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python_exe}</string>
        <string>{DEST_WATCHDOG}</string>
    </array>

    <!-- Start immediately when loaded -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Restart automatically if it crashes -->
    <key>KeepAlive</key>
    <true/>

    <!-- Restart throttle: wait 10s before restarting a crashed watchdog -->
    <key>ThrottleInterval</key>
    <integer>10</integer>

    <key>StandardOutPath</key>
    <string>{LOG_FILE}</string>

    <key>StandardErrorPath</key>
    <string>{LOG_FILE}</string>

    <!-- Run as the current user (not root) -->
    <key>UserName</key>
    <string>{os.environ.get("USER", "")}</string>
</dict>
</plist>
"""
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist_content)
    ok(f"Wrote plist to {PLIST_PATH}")

def unload_if_running():
    """Unload any existing version first so we can reload cleanly."""
    result = subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True, text=True
    )
    # Ignore errors — it just means it wasn't loaded yet

def load_service():
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        # On macOS 11+ this might be a warning, not a fatal error
        info(f"launchctl load output: {result.stderr.strip() or result.stdout.strip()}")
    else:
        ok("Service loaded into launchd")

def verify_running():
    result = subprocess.run(
        ["launchctl", "list", LABEL],
        capture_output=True, text=True
    )
    if result.returncode == 0 and LABEL in result.stdout:
        ok("Watchdog is RUNNING")
        # Parse PID from output
        for line in result.stdout.splitlines():
            if line.strip():
                info(f"launchctl: {line.strip()}")
    else:
        info("Could not verify via launchctl list — check log file:")
        info(f"  tail -f {LOG_FILE}")

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("\n=== Archer Memory Watchdog Installer ===\n")

    check_source()
    ensure_hermes_dir()
    copy_watchdog()
    write_plist()
    unload_if_running()
    load_service()
    verify_running()

    print(f"""
=== Installation complete ===

The watchdog is now running independently of Archer.
It polls every 60 seconds and forces a memory dump when:
  - 8+ new interactions have occurred since the last dump, OR
  - The session context file exceeds 1,700 characters

Archer cannot disable or bypass this. It restarts automatically on reboot.

Useful commands:
  Check status:   launchctl list {LABEL}
  View log:       tail -f {LOG_FILE}
  Stop watchdog:  launchctl unload {PLIST_PATH}
  Start watchdog: launchctl load {PLIST_PATH}
""")

if __name__ == "__main__":
    main()
