#!/bin/bash
# fix_archer.sh — Run on Mac terminal (NOT Pi SSH)
#
# What this does:
#   1. Kills the old Archer Telegram daemon (it races the Hermes gateway for messages)
#   2. Disables the daemon launchd entry so it stays dead after reboot
#   3. Archives Orange Pi context files that contaminate every Hermes request
#   4. Fixes HERMES_MODEL string in .env (dash → period format)
#   5. Kills the network-exposed PocketBase instance (security fix)
#   6. Restarts the Hermes gateway cleanly so it owns Telegram exclusively
#
# After this runs:
#   - Telegram messages go to Hermes gateway only (full skills, no race condition)
#   - PocketBase accessible only on localhost:8090
#   - Archer no longer confuses Mac with Orange Pi

set -e

echo ""
echo "======================================================"
echo "  Archer Fix — $(date)"
echo "======================================================"

# ── Step 1: Kill the Telegram daemon ──────────────────────
echo ""
echo "→ Step 1: Stopping Archer Telegram daemon..."
pkill -f archer_daemon.py 2>/dev/null || true
sleep 1
rm -rf /tmp/archer_telegram_bot.lock 2>/dev/null || true
echo "  ✓ Daemon process killed"

# ── Step 2: Disable daemon launchd entry ──────────────────
echo ""
echo "→ Step 2: Disabling daemon launchd entry..."
DAEMON_PLIST="$HOME/Library/LaunchAgents/com.archer.telegramdaemon.plist"
if [ -f "$DAEMON_PLIST" ]; then
    launchctl unload "$DAEMON_PLIST" 2>/dev/null || true
    # Rename so launchd ignores it on next boot (keeps it as backup)
    mv "$DAEMON_PLIST" "${DAEMON_PLIST}.disabled"
    echo "  ✓ Daemon plist disabled (renamed to .disabled)"
else
    echo "  ✓ Daemon plist not found (already gone or different path)"
fi

# ── Step 3: Archive Orange Pi context files ────────────────
echo ""
echo "→ Step 3: Archiving Orange Pi context files..."
HERMES="$HOME/.hermes"
ARCHIVE="$HERMES/archive_pi_context"
mkdir -p "$ARCHIVE"

PI_FILES=(
    "ORANGE_PI_BRIEFING_COMPLETE_CONTEXT.md"
    "ORANGE_PI_BUILD_STEPS.md"
    "ORANGE_PI_README.txt"
)
ARCHIVED=0
for f in "${PI_FILES[@]}"; do
    if [ -f "$HERMES/$f" ]; then
        mv "$HERMES/$f" "$ARCHIVE/$f"
        echo "  → Archived: $f"
        ARCHIVED=$((ARCHIVED + 1))
    fi
done
if [ $ARCHIVED -eq 0 ]; then
    echo "  ✓ No Pi context files found (already clean)"
else
    echo "  ✓ $ARCHIVED file(s) archived to $ARCHIVE"
fi

# ── Step 4: Fix HERMES_MODEL format in .env ───────────────
echo ""
echo "→ Step 4: Fixing HERMES_MODEL in .env..."
ENV_FILE="$HERMES/.env"
if grep -q "HERMES_MODEL=anthropic/claude-haiku-4-5$" "$ENV_FILE"; then
    sed -i '' 's|HERMES_MODEL=anthropic/claude-haiku-4-5$|HERMES_MODEL=anthropic/claude-haiku-4.5|' "$ENV_FILE"
    echo "  ✓ Fixed: anthropic/claude-haiku-4-5 → anthropic/claude-haiku-4.5"
else
    CURRENT=$(grep "HERMES_MODEL=" "$ENV_FILE")
    echo "  ✓ Already correct: $CURRENT"
fi

# ── Step 5: Kill network-exposed PocketBase ───────────────
echo ""
echo "→ Step 5: Fixing PocketBase exposure (security)..."
EXPOSED_PID=$(ps aux | grep "pocketbase serve --http=0.0.0.0:8090" | grep -v grep | awk '{print $2}')
if [ -n "$EXPOSED_PID" ]; then
    kill "$EXPOSED_PID"
    echo "  ✓ Killed exposed PocketBase PID $EXPOSED_PID (was on 0.0.0.0:8090)"
    echo "  ✓ PocketBase now accessible on localhost only (127.0.0.1:8090)"
else
    echo "  ✓ No exposed PocketBase found"
fi

# Brief pause — let processes settle
sleep 2

# Verify localhost PocketBase is still up
if ps aux | grep "pocketbase serve --http=127.0.0.1:8090" | grep -v grep > /dev/null; then
    echo "  ✓ Localhost PocketBase confirmed running"
else
    echo "  ⚠ WARNING: Localhost PocketBase not detected — check manually"
    echo "    Run: /Users/darrellcalton/pocketbase/pocketbase serve --http=127.0.0.1:8090 &"
fi

# ── Step 6: Restart Hermes gateway ────────────────────────
echo ""
echo "→ Step 6: Restarting Hermes gateway (cleanly owns Telegram now)..."
launchctl kickstart -k "gui/$UID/ai.hermes.gateway"
echo "  ✓ Gateway restarted"

sleep 3

# Confirm gateway is back up
if ps aux | grep "hermes_cli.main gateway" | grep -v grep > /dev/null; then
    echo "  ✓ Gateway process confirmed running"
else
    echo "  ⚠ Gateway process not detected yet — may still be starting"
fi

# ── Done ──────────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  Done. What changed:"
echo ""
echo "  • Telegram daemon: KILLED + disabled (no more race)"
echo "  • Hermes gateway: owns Telegram exclusively"
echo "  • Orange Pi files: archived (no more Pi confusion)"
echo "  • HERMES_MODEL: format corrected"
echo "  • PocketBase: localhost only (network exposure closed)"
echo ""
echo "  Test: Send Archer a message on Telegram."
echo "  He should respond with full skills + correct identity."
echo ""
echo "  Gateway log: tail -f ~/.hermes/logs/gateway.log"
echo "======================================================"
