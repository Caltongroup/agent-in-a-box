#!/usr/bin/env python3
"""
memory_watchdog.py — Deterministic memory fence for Archer
===========================================================
Runs as a SEPARATE PROCESS managed by launchd.
Archer has zero involvement in whether this fires.

Logic:
  Every 60 seconds, check how many interactions have been logged
  in PocketBase since the last confirmed dump.
  If that count >= DUMP_THRESHOLD, force memory_guardian.py dump.

The LLM cannot bypass this. It runs whether Archer is working
correctly or not.

Install with: python3 install_watchdog.py
Logs to:      ~/.hermes/watchdog.log
"""

import time
import subprocess
import logging
import json
import sys
from pathlib import Path
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────

DUMP_THRESHOLD_TURNS   = 8       # Force dump after this many new interactions
DUMP_THRESHOLD_CHARS   = 1700    # Force dump if context file exceeds this size
POLL_INTERVAL_SECONDS  = 60      # How often to check (seconds)

MEMORY_GUARDIAN  = Path("~/.hermes/memory_guardian.py").expanduser()
SESSION_CONTEXT  = Path("~/.hermes/session_context.md").expanduser()
POCKETBASE_DB    = Path("~/pocketbase/pb_data/data.db").expanduser()
STATE_FILE       = Path("~/.hermes/watchdog_state.json").expanduser()
LOG_FILE         = Path("~/.hermes/watchdog.log").expanduser()

# ── Logging setup ──────────────────────────────────────────────────────────────

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("watchdog")

# ── State persistence ─────────────────────────────────────────────────────────

def load_state() -> dict:
    """Load watchdog state from disk. Returns defaults if not found."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "last_dump_time": None,
        "interaction_count_at_last_dump": 0,
        "total_dumps_forced": 0,
    }

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ── PocketBase interaction count ───────────────────────────────────────────────

def get_interaction_count() -> int:
    """
    Count rows in agent_soul_interactions via SQLite directly.
    PocketBase stores its data in a standard SQLite file.
    Returns -1 if the table or DB is not accessible.
    """
    if not POCKETBASE_DB.exists():
        return -1
    try:
        import sqlite3
        conn = sqlite3.connect(str(POCKETBASE_DB), timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM agent_soul_interactions")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        log.warning(f"Could not read PocketBase: {e}")
        return -1

# ── Context size check ─────────────────────────────────────────────────────────

def get_context_size() -> int:
    """Return character count of the current session context file."""
    if SESSION_CONTEXT.exists():
        return len(SESSION_CONTEXT.read_text())
    return 0

# ── Dump enforcement ───────────────────────────────────────────────────────────

def force_dump(reason: str) -> bool:
    """
    Run memory_guardian.py dump unconditionally.
    Returns True on success, False on failure.
    """
    if not MEMORY_GUARDIAN.exists():
        log.error(f"memory_guardian.py not found at {MEMORY_GUARDIAN}. Cannot dump.")
        return False

    log.info(f"FORCING DUMP — reason: {reason}")
    try:
        result = subprocess.run(
            [sys.executable, str(MEMORY_GUARDIAN), "dump"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            log.info(f"Dump completed successfully.")
            if result.stdout.strip():
                log.info(f"Output: {result.stdout.strip()}")
            return True
        else:
            log.error(f"Dump failed (exit {result.returncode}): {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        log.error("Dump timed out after 30 seconds.")
        return False
    except Exception as e:
        log.error(f"Dump error: {e}")
        return False

# ── Main watch loop ────────────────────────────────────────────────────────────

def run():
    log.info("=== Watchdog started ===")
    log.info(f"Thresholds: {DUMP_THRESHOLD_TURNS} turns | {DUMP_THRESHOLD_CHARS} chars | poll every {POLL_INTERVAL_SECONDS}s")

    state = load_state()
    log.info(f"State loaded: {state}")

    while True:
        try:
            current_count  = get_interaction_count()
            context_size   = get_context_size()
            turns_since    = max(0, current_count - state["interaction_count_at_last_dump"])

            log.debug(f"interactions={current_count} turns_since_dump={turns_since} context_chars={context_size}")

            dump_reason = None

            if current_count >= 0 and turns_since >= DUMP_THRESHOLD_TURNS:
                dump_reason = f"{turns_since} turns since last dump (threshold: {DUMP_THRESHOLD_TURNS})"

            elif context_size >= DUMP_THRESHOLD_CHARS:
                dump_reason = f"context size {context_size} chars (threshold: {DUMP_THRESHOLD_CHARS})"

            if dump_reason:
                success = force_dump(dump_reason)
                if success:
                    # Re-read count after dump in case guardian added rows
                    new_count = get_interaction_count()
                    state["last_dump_time"] = datetime.now().isoformat()
                    state["interaction_count_at_last_dump"] = new_count if new_count >= 0 else current_count
                    state["total_dumps_forced"] += 1
                    save_state(state)
                    log.info(f"State saved. Total forced dumps: {state['total_dumps_forced']}")

        except Exception as e:
            log.error(f"Watchdog loop error (continuing): {e}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
