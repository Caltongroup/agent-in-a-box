#!/usr/bin/env bash
# =============================================================================
# deploy_stack.sh — Agent in a Box: Full Stack Deployer
# Target: Orange Pi 5 Pro (RK3588S, ARM64) running Armbian Trixie
# Idempotent: safe to run multiple times
# Usage: sudo bash deploy_stack.sh
# =============================================================================

set -euo pipefail

# ── OS check ─────────────────────────────────────────────────────────────────
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "✗ This script is for Linux (ARM64) only. Run it on the Pi, not your Mac."
    exit 1
fi

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $1${NC}"; }
info() { echo -e "${CYAN}→ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
die()  { echo -e "${RED}✗ $1${NC}"; exit 1; }

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR="/home/pi/data"
NVME_DEV="/dev/nvme0n1"
OLLAMA_MODELS_DIR="${DATA_DIR}/ollama"
PB_DIR="${DATA_DIR}/pocketbase"
HERMES_DIR="${DATA_DIR}/hermes"
AGENTS_DIR="${DATA_DIR}/agents"
DOCS_DIR="${DATA_DIR}/documents"
VENV_DIR="${DATA_DIR}/venv"

PB_VERSION="0.23.4"
PB_ZIP="pocketbase_${PB_VERSION}_linux_arm64.zip"
PB_URL="https://github.com/pocketbase/pocketbase/releases/download/v${PB_VERSION}/${PB_ZIP}"

OLLAMA_MODELS=("phi3.5" "nomic-embed-text")

HERMES_REPO="https://github.com/Caltongroup/GoldenImage_Files.git"

# ── Root check ────────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Run as root: sudo bash deploy_stack.sh"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     Agent in a Box — Stack Deployer      ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — System packages
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 1/8 — Installing system dependencies"
apt-get update -qq
apt-get install -y -qq curl wget unzip zstd python3 python3-pip python3-venv lshw git
ok "System packages ready"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — NVMe SSD mount
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 2/8 — NVMe SSD"

if ! lsblk | grep -q nvme0n1; then
    die "NVMe device ${NVME_DEV} not found. Is the SSD seated properly?"
fi

# Format only if no filesystem present
if ! blkid "${NVME_DEV}" &>/dev/null; then
    info "No filesystem on ${NVME_DEV} — formatting ext4"
    mkfs.ext4 -q "${NVME_DEV}"
    ok "Formatted ${NVME_DEV} as ext4"
else
    ok "Filesystem already exists on ${NVME_DEV}"
fi

# Mount if not already mounted
if ! mountpoint -q "${DATA_DIR}"; then
    mkdir -p "${DATA_DIR}"
    mount "${NVME_DEV}" "${DATA_DIR}"
    ok "Mounted ${NVME_DEV} → ${DATA_DIR}"
else
    ok "${DATA_DIR} already mounted"
fi

# fstab entry (idempotent)
if ! grep -q "${NVME_DEV}" /etc/fstab; then
    echo "${NVME_DEV} ${DATA_DIR} ext4 defaults 0 2" >> /etc/fstab
    ok "Added fstab entry"
else
    ok "fstab entry already present"
fi

# Directory structure
mkdir -p "${OLLAMA_MODELS_DIR}" "${PB_DIR}" "${HERMES_DIR}" "${AGENTS_DIR}" "${DOCS_DIR}"
ok "SSD directory structure ready"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Ollama
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 3/8 — Ollama"

# Pin model storage to SSD before install
if ! grep -q "OLLAMA_MODELS" /etc/environment; then
    echo "OLLAMA_MODELS=${OLLAMA_MODELS_DIR}" >> /etc/environment
fi
export OLLAMA_MODELS="${OLLAMA_MODELS_DIR}"

if command -v ollama &>/dev/null; then
    ok "Ollama already installed: $(ollama --version 2>/dev/null | head -1)"
else
    curl -fsSL https://ollama.com/install.sh | sh
    ok "Ollama installed"
fi

# Patch systemd service to use SSD for models
OLLAMA_SERVICE="/etc/systemd/system/ollama.service"
if [[ -f "${OLLAMA_SERVICE}" ]] && ! grep -q "OLLAMA_MODELS" "${OLLAMA_SERVICE}"; then
    sed -i '/\[Service\]/a Environment="OLLAMA_MODELS='"${OLLAMA_MODELS_DIR}"'"' "${OLLAMA_SERVICE}"
    systemctl daemon-reload
    ok "Ollama service patched: models → SSD"
fi

systemctl enable ollama &>/dev/null
systemctl restart ollama
sleep 3

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Pull models
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 4/8 — Pulling Ollama models (this takes a while)"

for model in "${OLLAMA_MODELS[@]}"; do
    if ollama list 2>/dev/null | grep -q "^${model}"; then
        ok "Model already present: ${model}"
    else
        info "Pulling ${model}..."
        ollama pull "${model}"
        ok "Pulled: ${model}"
    fi
done

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5 — PocketBase
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 5/8 — PocketBase v${PB_VERSION}"

if [[ -f "${PB_DIR}/pocketbase" ]]; then
    ok "PocketBase binary already present"
else
    info "Downloading PocketBase..."
    wget -q "${PB_URL}" -O "/tmp/${PB_ZIP}"
    unzip -q "/tmp/${PB_ZIP}" -d "${PB_DIR}"
    chmod +x "${PB_DIR}/pocketbase"
    rm "/tmp/${PB_ZIP}"
    ok "PocketBase installed → ${PB_DIR}"
fi

# Systemd service for PocketBase
PB_SERVICE="/etc/systemd/system/pocketbase.service"
if [[ ! -f "${PB_SERVICE}" ]]; then
    cat > "${PB_SERVICE}" << EOF
[Unit]
Description=PocketBase
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=${PB_DIR}
ExecStart=${PB_DIR}/pocketbase serve --http=0.0.0.0:8090
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable pocketbase
    ok "PocketBase service created and enabled"
else
    ok "PocketBase service already exists"
fi

systemctl start pocketbase
sleep 2
ok "PocketBase running on :8090"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6 — Python venv + AgentSoul SDK
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 6/8 — Python venv + AgentSoul SDK"

if [[ ! -d "${VENV_DIR}" ]]; then
    python3 -m venv "${VENV_DIR}"
    ok "Created venv → ${VENV_DIR}"
else
    ok "Venv already exists"
fi

# Activate and install
source "${VENV_DIR}/bin/activate"

pip install --quiet --upgrade pip
pip install --quiet agentsoul chromadb requests pyyaml

ok "Python packages installed"
deactivate

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7 — Hermes core
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 7/8 — Hermes core"

if [[ -d "${HERMES_DIR}/.git" ]]; then
    info "Hermes repo exists — pulling latest"
    git -C "${HERMES_DIR}" pull --quiet
    ok "Hermes updated"
else
    info "Cloning Hermes from ${HERMES_REPO}"
    if git clone --quiet "${HERMES_REPO}" "${HERMES_DIR}" 2>/dev/null; then
        ok "Hermes cloned → ${HERMES_DIR}"
    else
        warn "Could not clone Hermes repo (check network/auth). Skipping — run manually."
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 8 — Ownership + onboard wizard
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 8/8 — Permissions"
chown -R pi:pi "${DATA_DIR}"
ok "Ownership set: pi:pi on ${DATA_DIR}"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         Stack deploy complete ✓          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  NVMe mounted  : ${CYAN}${DATA_DIR}${NC}"
echo -e "  Ollama models : ${CYAN}${OLLAMA_MODELS_DIR}${NC}"
echo -e "  PocketBase    : ${CYAN}http://$(hostname -I | awk '{print $1}'):8090/_${NC}"
echo -e "  Python venv   : ${CYAN}${VENV_DIR}${NC}"
echo -e "  Agents home   : ${CYAN}${AGENTS_DIR}${NC}"
echo ""
echo -e "${YELLOW}Next step: run the onboarding wizard${NC}"
echo -e "  ${CYAN}cd ${DATA_DIR} && source venv/bin/activate && python3 hermes/onboard_wizard.py${NC}"
echo ""
