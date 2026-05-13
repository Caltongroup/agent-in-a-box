#!/usr/bin/env bash
# =============================================================================
# install_services.sh — Penelope: Agent in a Box
# Installs and enables all systemd services for the current deployment.
# Called at end of onboard_wizard.py. Fully idempotent.
#
# Usage:
#   sudo bash install_services.sh <project_dir> <soul_path> \
#                                  <telegram_token> <telegram_chat_id>
#
# All args optional — defaults are placeholders you can edit in service files.
# =============================================================================

set -euo pipefail

PROJECT_DIR="${1:-/home/pi/my_organization_agent}"
SOUL_PATH="${2:-${PROJECT_DIR}/SOUL.md}"
TELEGRAM_TOKEN="${3:-your-telegram-bot-token-here}"
TELEGRAM_CHAT_ID="${4:-your-chat-id-here}"
COLLECTION="$(basename "${PROJECT_DIR}" _agent)"

SYSTEMD_DIR="/etc/systemd/system"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "  Penelope: Installing systemd services…"
echo ""

# Helper — copy a service file verbatim
install_service() {
    local name="$1"
    local src="${SCRIPT_DIR}/${name}.service"
    if [[ ! -f "$src" ]]; then
        echo "  ⚠  Missing: ${src} — skipping ${name}"; return
    fi
    cp "$src" "${SYSTEMD_DIR}/${name}.service"
    echo "  ✓  Installed  ${name}.service"
}

# 1. Ollama
install_service ollama

# 2. PocketBase
install_service pocketbase

# 3. Watcher (inject project paths + collection)
sed \
    -e "s|Environment=PROJECT_DIR=.*|Environment=PROJECT_DIR=${PROJECT_DIR}|" \
    -e "s|Environment=COLLECTION=.*|Environment=COLLECTION=${COLLECTION}|" \
    "${SCRIPT_DIR}/watcher.service" > "${SYSTEMD_DIR}/watcher.service"
echo "  ✓  Installed  watcher.service  (collection: ${COLLECTION})"

# 4. Hermes Agent (inject project paths)
sed \
    -e "s|Environment=PROJECT_DIR=.*|Environment=PROJECT_DIR=${PROJECT_DIR}|" \
    -e "s|Environment=SOUL_PATH=.*|Environment=SOUL_PATH=${SOUL_PATH}|" \
    "${SCRIPT_DIR}/hermes-agent.service" > "${SYSTEMD_DIR}/hermes-agent.service"
echo "  ✓  Installed  hermes-agent.service"

# 5. Hermes Gateway (inject Telegram token)
sed \
    -e "s|Environment=TELEGRAM_TOKEN=.*|Environment=TELEGRAM_TOKEN=${TELEGRAM_TOKEN}|" \
    "${SCRIPT_DIR}/hermes-gateway.service" > "${SYSTEMD_DIR}/hermes-gateway.service"
echo "  ✓  Installed  hermes-gateway.service"

# 6. Hermes Web UI (inject project paths + collection + agent name)
AGENT_NAME="$(grep '^\*\*Name:\*\*' "${SOUL_PATH}" 2>/dev/null | sed 's/\*\*Name:\*\* //' | tr -d '\r' || echo 'Penelope')"
sed \
    -e "s|AGENT_PROJECT_PATH|${PROJECT_DIR}|g" \
    -e "s|VENV_PATH|/home/pi/penelope_venv|g" \
    -e "s|GOLDENIMAGE_PATH|/home/pi/GoldenImage_Files|g" \
    -e "s|AGENT_NAME|${AGENT_NAME}|g" \
    "${SCRIPT_DIR}/hermes-webui.service" > "${SYSTEMD_DIR}/hermes-webui.service"
echo "  ✓  Installed  hermes-webui.service  (agent: ${AGENT_NAME})"

# 7. Boot Notify (inject Telegram token + chat ID)
sed \
    -e "s|Environment=TELEGRAM_TOKEN=.*|Environment=TELEGRAM_TOKEN=${TELEGRAM_TOKEN}|" \
    -e "s|Environment=TELEGRAM_CHAT_ID=.*|Environment=TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}|" \
    "${SCRIPT_DIR}/penelope-notify.service" > "${SYSTEMD_DIR}/penelope-notify.service"
echo "  ✓  Installed  penelope-notify.service"

# Tailscale — not managed by us, just verify
echo ""
if systemctl is-enabled tailscaled >/dev/null 2>&1; then
    echo "  ✓  Tailscale (tailscaled) already enabled"
else
    echo "  ⚠  Tailscale not found. Install:"
    echo "       curl -fsSL https://tailscale.com/install.sh | sh"
    echo "       sudo tailscale up"
fi

# Reload + enable + start
echo ""
systemctl daemon-reload

for svc in ollama pocketbase watcher hermes-agent hermes-webui hermes-gateway penelope-notify; do
    systemctl enable  "${svc}" 2>/dev/null && echo "  ✓  Enabled   ${svc}"
    systemctl restart "${svc}" 2>/dev/null && echo "  ✓  Started   ${svc}" \
        || echo "  ⚠  ${svc} did not start — check: journalctl -u ${svc} -n 20"
done

echo ""
echo "  All services installed. Verify:"
echo "    sudo systemctl status ollama pocketbase watcher hermes-agent"
echo ""
echo "  Pre-demo health check:"
echo "    python3 ~/penelope_demo_test.py"
echo ""
