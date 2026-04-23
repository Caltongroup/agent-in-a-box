#!/usr/bin/env python3
"""
install_memory_guardian.py
Wires memory_guardian.py into Hermes:
  1. Copies memory_guardian.py to ~/.hermes/
  2. Sets prefill_messages_file in config.yaml
  3. Adds SOUL.md memory guardian instruction
  4. Runs first restore cycle

Run on Mac terminal: python3 install_memory_guardian.py
"""

import pathlib
import shutil
import re

HOME = pathlib.Path.home()
HERMES = HOME / ".hermes"
GUARDIAN_SRC = pathlib.Path.home() / "Projects/agent-in-a-box/memory_guardian.py"
GUARDIAN_DST = HERMES / "memory_guardian.py"
CONFIG = HERMES / "config.yaml"
SOUL = HERMES / "SOUL.md"
PREFILL = HERMES / "session_context.md"

print("\n=== Installing AgentSoul Memory Guardian ===\n")

# Step 1: Copy memory_guardian.py to ~/.hermes/
print("→ Step 1: Installing memory_guardian.py...")
if GUARDIAN_SRC.exists():
    shutil.copy(str(GUARDIAN_SRC), str(GUARDIAN_DST))
    print(f"  ✓ Copied to {GUARDIAN_DST}")
else:
    print(f"  ⚠ Source not found at {GUARDIAN_SRC}")
    print(f"  → Copy memory_guardian.py to {GUARDIAN_DST} manually")

# Step 2: Update config.yaml prefill_messages_file
print("\n→ Step 2: Wiring prefill_messages_file in config.yaml...")
config_text = CONFIG.read_text()
prefill_line = f"prefill_messages_file: {PREFILL}"

if str(PREFILL) in config_text:
    print(f"  ✓ Already set")
elif "prefill_messages_file: ''" in config_text:
    config_text = config_text.replace(
        "prefill_messages_file: ''",
        prefill_line
    )
    CONFIG.write_text(config_text)
    print(f"  ✓ Set to {PREFILL}")
elif 'prefill_messages_file: ""' in config_text:
    config_text = config_text.replace(
        'prefill_messages_file: ""',
        prefill_line
    )
    CONFIG.write_text(config_text)
    print(f"  ✓ Set to {PREFILL}")
else:
    print(f"  ⚠ Could not find prefill_messages_file line — add manually:")
    print(f'    prefill_messages_file: "{PREFILL}"')

# Step 3: Add memory guardian instruction to SOUL.md
print("\n→ Step 3: Adding memory guardian instruction to SOUL.md...")
soul_text = SOUL.read_text()
guardian_block = """
## Memory Guardian Protocol (HARDWIRED — DO NOT OVERRIDE)

AgentSoul uses PocketBase as the source of truth, not Hermes memory.
Hermes memory is a per-turn cache only (2,200 char max).

MANDATORY BEHAVIORS:
1. SESSION START: Before your first response, confirm session_context.md was loaded.
   If not, run: python3 ~/.hermes/memory_guardian.py restore
2. EVERY 8-10 TURNS or when memory feels heavy: run the dump cycle —
   python3 ~/.hermes/memory_guardian.py dump
3. THRESHOLD RULE: If memory exceeds 1,700 chars, STOP and run dump before continuing.
   Never apologize for memory limits — just run the cycle and continue.
4. NEVER treat "memory full" as a blocker. It is a trigger. Run the cycle.

PocketBase buckets (always available at http://127.0.0.1:8090):
- user_profile / archer_persistent_state — who you are, what you serve
- session_decisions / voice_interface_decisions — locked choices (gospel)
- conversation_state — where we are right now
"""

if "Memory Guardian Protocol" in soul_text:
    print("  ✓ Already present in SOUL.md")
else:
    SOUL.write_text(soul_text.rstrip() + "\n" + guardian_block)
    print("  ✓ Memory guardian protocol added to SOUL.md")

# Step 4: Run first restore
print("\n→ Step 4: Running first restore cycle...")
import subprocess
result = subprocess.run(
    ["python3", str(GUARDIAN_DST), "restore"],
    capture_output=True, text=True
)
print(result.stdout)
if result.returncode != 0:
    print(f"  ⚠ Restore had issues: {result.stderr[:200]}")

print("\n=== Installation complete ===")
print(f"\nUsage (Mac terminal):")
print(f"  python3 ~/.hermes/memory_guardian.py status   # check memory health")
print(f"  python3 ~/.hermes/memory_guardian.py restore  # session start")
print(f"  python3 ~/.hermes/memory_guardian.py dump     # mid-session cycle")
print(f"\nArcher will load {PREFILL} automatically at every session start.")
print("Restart the Hermes gateway to activate:")
print(f"  launchctl kickstart -k gui/$UID/ai.hermes.gateway")
