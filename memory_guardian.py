#!/usr/bin/env python3
"""
memory_guardian.py — AgentSoul Persistence Guardrail
=====================================================
Solves the Hermes 2,200-char memory limit by using PocketBase as the
real source of truth and Hermes memory as a per-turn cache only.

Three modes:
  python3 memory_guardian.py restore   — session start: query PocketBase → write prefill file
  python3 memory_guardian.py dump      — mid-session: dump Hermes memory → PocketBase, refresh prefill
  python3 memory_guardian.py status    — show memory health + PocketBase state

Tables used (verified April 22 2026):
  archer_persistent_state  — agent identity, project_state JSON, decisions_locked JSON, user_context
  voice_interface_decisions — decision, rationale, status (filter: status='locked')
  agent_soul_interactions  — message, response, interaction_type, timestamp, agent_id

Hermes picks up restored context via:
  prefill_messages_file: ~/.hermes/session_context.md  (set in config.yaml)

Run on: Mac mini (NOT Orange Pi)
"""

import sys
import json
import sqlite3
import pathlib
import datetime
import argparse
import subprocess

# ── Config ─────────────────────────────────────────────────────────────────────
PB_DB        = pathlib.Path.home() / "pocketbase/pb_data/data.db"
PREFILL_FILE = pathlib.Path.home() / ".hermes/session_context.md"
HERMES_MEM   = pathlib.Path.home() / ".hermes/memories"
AGENT_ID     = "archer_001"
THRESHOLD    = 1700   # chars — dump cycle triggers above this
HARD_LIMIT   = 2200   # chars — Hermes hard ceiling
TIMESTAMP    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


# ── PocketBase direct SQLite access ────────────────────────────────────────────
def db(sql, params=()):
    """Query PocketBase SQLite directly — no REST, no auth needed."""
    if not PB_DB.exists():
        print(f"  ⚠ PocketBase DB not found at {PB_DB}")
        return []
    conn = sqlite3.connect(str(PB_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as e:
        print(f"  ⚠ Query failed: {e}")
        return []
    finally:
        conn.close()


def db_write(sql, params=()):
    """Execute a write against PocketBase SQLite."""
    if not PB_DB.exists():
        print(f"  ⚠ PocketBase DB not found at {PB_DB}")
        return False
    conn = sqlite3.connect(str(PB_DB))
    try:
        conn.execute(sql, params)
        conn.commit()
        return True
    except sqlite3.OperationalError as e:
        print(f"  ⚠ Write failed: {e}")
        return False
    finally:
        conn.close()


# ── Read Hermes memory files ────────────────────────────────────────────────────
def read_hermes_memory():
    """Read ~/.hermes/memories/*.md and return (combined_text, char_count)."""
    if not HERMES_MEM.exists():
        return "", 0
    parts = []
    for f in sorted(HERMES_MEM.glob("*.md")):
        try:
            content = f.read_text().strip()
            if content:
                parts.append(f"[{f.stem}]\n{content}")
        except Exception:
            pass
    text = "\n\n".join(parts)
    return text, len(text)


def clear_hermes_memory():
    """Wipe content of all Hermes memory files (keeps the files, empties them)."""
    if not HERMES_MEM.exists():
        return 0
    cleared = 0
    for f in HERMES_MEM.glob("*.md"):
        try:
            f.write_text("")
            cleared += 1
        except Exception as e:
            print(f"  ⚠ Could not clear {f.name}: {e}")
    return cleared


# ── Fetch context from PocketBase ───────────────────────────────────────────────
def get_agent_state():
    """Get Archer's persistent state record."""
    rows = db(
        "SELECT agent_id, user_context, decisions_locked, project_state, "
        "last_session_timestamp, session_count "
        "FROM archer_persistent_state WHERE agent_id = ? LIMIT 1",
        (AGENT_ID,)
    )
    if not rows:
        # Try without agent_id filter — might use different ID
        rows = db(
            "SELECT agent_id, user_context, decisions_locked, project_state, "
            "last_session_timestamp, session_count "
            "FROM archer_persistent_state LIMIT 1"
        )
    return rows[0] if rows else {}


def get_locked_decisions():
    """Get locked decisions from voice_interface_decisions."""
    return db(
        "SELECT decision, rationale, status FROM voice_interface_decisions "
        "WHERE status = 'locked' ORDER BY created DESC LIMIT 10"
    )


def get_recent_interactions():
    """Get last 5 conversation turns from agent_soul_interactions."""
    return db(
        "SELECT message, response, timestamp FROM agent_soul_interactions "
        "WHERE agent_id = ? AND interaction_type != 'memory_dump' "
        "ORDER BY created DESC LIMIT 5",
        (AGENT_ID,)
    )


# ── Write context prefill file ──────────────────────────────────────────────────
def write_prefill(state, decisions, interactions):
    """Write ~/.hermes/session_context.md with real PocketBase data."""
    lines = [
        f"[AGENTSOUL CONTEXT RESTORED — {TIMESTAMP}]",
        "Source of truth: PocketBase. This overrides any conflicting memory.",
        "Do NOT re-derive — use exactly as written below.",
        "",
    ]

    # Agent state / user context
    if state:
        lines.append("## Agent State")
        if state.get("user_context"):
            lines.append(f"User context: {state['user_context']}")
        if state.get("last_session_timestamp"):
            lines.append(f"Last session: {state['last_session_timestamp']}")
        if state.get("session_count"):
            lines.append(f"Session count: {state['session_count']}")

        # Parse project_state JSON if present
        proj = state.get("project_state")
        if proj:
            try:
                proj_data = json.loads(proj) if isinstance(proj, str) else proj
                if proj_data:
                    lines.append(f"Project state: {json.dumps(proj_data, separators=(',', ':'))[:300]}")
            except Exception:
                pass

        # Parse decisions_locked JSON if present
        locked = state.get("decisions_locked")
        if locked:
            try:
                locked_data = json.loads(locked) if isinstance(locked, str) else locked
                if locked_data:
                    lines.append(f"Decisions locked: {json.dumps(locked_data, separators=(',', ':'))[:300]}")
            except Exception:
                pass
        lines.append("")

    # Locked decisions from voice_interface_decisions table
    if decisions:
        lines.append("## Locked Decisions (Gospel — Do Not Override)")
        for d in decisions:
            decision = d.get("decision", "")
            rationale = d.get("rationale", "")
            entry = f"- {decision}"
            if rationale:
                entry += f" ({rationale[:80]})"
            lines.append(entry)
        lines.append("")

    # Recent conversation context
    if interactions:
        lines.append("## Recent Context (last turns)")
        for i in reversed(interactions):  # Chronological order
            ts = (i.get("timestamp") or "")[:16]
            msg = (i.get("message") or "")[:100]
            resp = (i.get("response") or "")[:150]
            lines.append(f"- [{ts}] Q: {msg}")
            if resp:
                lines.append(f"  A: {resp}")
        lines.append("")

    lines += [
        "---",
        "Hermes memory buffer = THIS TURN ONLY. Everything above is the source of truth.",
        ""
    ]

    content = "\n".join(lines)
    PREFILL_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREFILL_FILE.write_text(content)
    return len(content)


# ── RESTORE: Session start ──────────────────────────────────────────────────────
def cmd_restore():
    """Query PocketBase with real columns and write the prefill file."""
    print(f"→ Restoring context from PocketBase ({PB_DB.name})...")

    state        = get_agent_state()
    decisions    = get_locked_decisions()
    interactions = get_recent_interactions()

    prefill_len = write_prefill(state, decisions, interactions)
    print(f"  ✓ Prefill written: {prefill_len} chars → {PREFILL_FILE}")
    print(f"  ✓ Agent state: {'found' if state else 'not found'}")
    print(f"  ✓ Locked decisions: {len(decisions)}")
    print(f"  ✓ Recent interactions: {len(interactions)}")

    mem_text, mem_chars = read_hermes_memory()
    bar_pct = int((mem_chars / HARD_LIMIT) * 100)
    print(f"  Memory buffer: {mem_chars}/{HARD_LIMIT} chars ({bar_pct}%)")
    if mem_chars > THRESHOLD:
        print(f"  ⚠ Memory already above threshold — run dump now")

    print(f"\n✓ Restore complete.")
    print(f"  Verify config.yaml has: prefill_messages_file: {PREFILL_FILE}")


# ── DUMP: Mid-session memory cycle ─────────────────────────────────────────────
def cmd_dump():
    """
    Dump Hermes memory to PocketBase, clear the buffer, restore fresh context.
    Triggered automatically when memory > 1,700 chars.
    """
    print(f"→ Memory dump cycle — {TIMESTAMP}")

    mem_text, mem_chars = read_hermes_memory()
    print(f"  Memory buffer: {mem_chars}/{HARD_LIMIT} chars")

    if mem_chars > 0:
        # Write to agent_soul_interactions as a memory_dump entry
        ts = datetime.datetime.utcnow().isoformat()
        rid = f"dump_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ok = db_write(
            "INSERT OR REPLACE INTO agent_soul_interactions "
            "(id, agent_id, entity_id, interaction_type, message, response, timestamp, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (rid, AGENT_ID, "memory_guardian", "memory_dump",
             f"MEMORY DUMP ({mem_chars} chars)", mem_text, ts, ts)
        )
        if ok:
            print(f"  ✓ Memory dumped to agent_soul_interactions (id: {rid})")

        # Clear Hermes memory
        cleared = clear_hermes_memory()
        print(f"  ✓ Cleared {cleared} Hermes memory file(s)")
    else:
        print(f"  Memory is empty — skipping dump")

    # Restore fresh context from PocketBase
    print(f"  → Refreshing prefill from PocketBase...")
    cmd_restore()
    print(f"\n✓ Dump cycle complete — context refreshed. Continue conversation naturally.")


# ── STATUS ──────────────────────────────────────────────────────────────────────
def cmd_status():
    """Show memory health and PocketBase state."""
    mem_text, mem_chars = read_hermes_memory()
    bar_pct = int((mem_chars / HARD_LIMIT) * 100)
    bar = "█" * (bar_pct // 10) + "░" * (10 - bar_pct // 10)

    print(f"\n=== AgentSoul Memory Status — {TIMESTAMP} ===\n")
    print(f"Hermes memory: {mem_chars}/{HARD_LIMIT} chars  [{bar}] {bar_pct}%")
    if mem_chars > THRESHOLD:
        print(f"  ⚠ ABOVE THRESHOLD ({THRESHOLD}) — run: python3 memory_guardian.py dump")
    elif mem_chars > 1400:
        print(f"  → Approaching threshold — monitor")
    else:
        print(f"  ✓ Healthy")

    print(f"\nPocketBase: {PB_DB} ({'exists' if PB_DB.exists() else 'NOT FOUND'})")
    print(f"Prefill:    {PREFILL_FILE} ({'exists' if PREFILL_FILE.exists() else 'missing — run restore'})")

    state = get_agent_state()
    decisions = get_locked_decisions()
    interactions = get_recent_interactions()
    dumps = db(
        "SELECT COUNT(*) as n FROM agent_soul_interactions "
        "WHERE interaction_type = 'memory_dump'"
    )

    print(f"\nPocketBase state:")
    print(f"  archer_persistent_state: {'found' if state else 'empty'}")
    print(f"  locked decisions: {len(decisions)}")
    print(f"  recent interactions: {len(interactions)}")
    print(f"  memory dumps logged: {dumps[0]['n'] if dumps else 0}")

    all_tables = db("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '\\_%' ESCAPE '\\'")
    print(f"\nAll user tables: {len(all_tables)} — run `.tables` in sqlite3 for full list")


# ── Main ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AgentSoul Memory Guardian — keeps Archer's context alive across Hermes memory limits"
    )
    parser.add_argument(
        "command",
        choices=["restore", "dump", "status"],
        help="restore = session start  |  dump = mid-session cycle  |  status = health check"
    )
    args = parser.parse_args()

    cmds = {"restore": cmd_restore, "dump": cmd_dump, "status": cmd_status}
    cmds[args.command]()
