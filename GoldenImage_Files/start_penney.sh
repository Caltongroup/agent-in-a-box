#!/bin/bash
# =============================================================================
# start_penney.sh — Launch Penney Web UI
# Double-click this file on the Pi desktop to start the agent.
# =============================================================================

VENV="$HOME/penelope_venv"
SCRIPT="$HOME/GoldenImage_Files/hermes/web_ui.py"

# Find the agent folder (first match of *_agent in home directory)
AGENT_DIR=$(find "$HOME" -maxdepth 1 -type d -name "*_agent" | head -1)

if [ -z "$AGENT_DIR" ]; then
    zenity --error --text="No agent folder found.\nRun the onboard wizard first:\npython3 ~/GoldenImage_Files/onboard_wizard.py" 2>/dev/null \
        || echo "ERROR: No agent folder found. Run onboard_wizard.py first."
    exit 1
fi

SOUL="$AGENT_DIR/SOUL.md"
CHROMA="$AGENT_DIR/chroma_db"
AGENT_NAME=$(grep "^\*\*Name:\*\*" "$SOUL" 2>/dev/null | sed 's/\*\*Name:\*\* //' | tr -d '\r' || basename "$AGENT_DIR" | sed 's/_agent//')

# Check if already running
if pgrep -f "web_ui.py" > /dev/null; then
    zenity --info --text="$AGENT_NAME is already running.\nOpen your browser to:\nhttp://$(hostname -I | awk '{print $1}'):5000" 2>/dev/null \
        || echo "$AGENT_NAME already running at http://$(hostname -I | awk '{print $1}'):5000"
    exit 0
fi

# Activate venv and launch
source "$VENV/bin/activate"

# Show launch notification
zenity --info --timeout=3 \
    --text="Starting $AGENT_NAME...\n\nOpen your browser to:\nhttp://$(hostname -I | awk '{print $1}'):5000" 2>/dev/null \
    || echo "Starting $AGENT_NAME at http://$(hostname -I | awk '{print $1}'):5000"

# Start the web UI (extract collection name from chroma_db if possible)
COLLECTION=$(basename "$AGENT_DIR" | sed 's/_agent//')

python3 "$SCRIPT" \
    --soul "$SOUL" \
    --chroma-db "$CHROMA" \
    --collection "$COLLECTION" \
    --agent-name "$AGENT_NAME"
