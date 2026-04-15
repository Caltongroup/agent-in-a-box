#!/usr/bin/env bash
# =============================================================================
# deploy_stack.sh — Agent in a Box: Full Stack Deployer v2
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
AGENTS_DIR="${DATA_DIR}/agents"
VENV_DIR="${DATA_DIR}/venv"
LLAMA_DIR="${DATA_DIR}/llama.cpp"
LLAMA_BIN="${LLAMA_DIR}/build/bin/llama-server"

PB_VERSION="0.23.4"
PB_ZIP="pocketbase_${PB_VERSION}_linux_arm64.zip"
PB_URL="https://github.com/pocketbase/pocketbase/releases/download/v${PB_VERSION}/${PB_ZIP}"

INFERENCE_MODEL="qwen2.5:1.5b"
EMBED_MODEL="nomic-embed-text"

LLAMA_PORT=8080
WEB_PORT=5000

# ── Root check ────────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Run as root: sudo bash deploy_stack.sh"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Agent in a Box — Stack Deployer v2     ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — System packages
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 1/10 — Installing system dependencies"
apt-get update -qq
apt-get install -y -qq \
    curl wget unzip zstd git lshw \
    python3 python3-pip python3-venv \
    cmake build-essential \
    glslang-tools
ok "System packages ready"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — NVMe SSD mount
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 2/10 — NVMe SSD"

if ! lsblk | grep -q nvme0n1; then
    die "NVMe device ${NVME_DEV} not found. Is the SSD seated properly?"
fi

if ! blkid "${NVME_DEV}" &>/dev/null; then
    info "No filesystem on ${NVME_DEV} — formatting ext4"
    mkfs.ext4 -q "${NVME_DEV}"
    ok "Formatted ${NVME_DEV} as ext4"
else
    ok "Filesystem already exists on ${NVME_DEV}"
fi

if ! mountpoint -q "${DATA_DIR}"; then
    mkdir -p "${DATA_DIR}"
    mount "${NVME_DEV}" "${DATA_DIR}"
    ok "Mounted ${NVME_DEV} → ${DATA_DIR}"
else
    ok "${DATA_DIR} already mounted"
fi

if ! grep -q "${NVME_DEV}" /etc/fstab; then
    echo "${NVME_DEV} ${DATA_DIR} ext4 defaults 0 2" >> /etc/fstab
    ok "Added fstab entry"
else
    ok "fstab entry already present"
fi

mkdir -p "${OLLAMA_MODELS_DIR}" "${PB_DIR}" "${AGENTS_DIR}" "${VENV_DIR}"
chmod 755 /home/pi "${DATA_DIR}"
ok "SSD directory structure ready"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Ollama (embeddings only)
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 3/10 — Ollama (embeddings + model download)"

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

OLLAMA_SERVICE="/etc/systemd/system/ollama.service"
if [[ -f "${OLLAMA_SERVICE}" ]] && ! grep -q "OLLAMA_MODELS" "${OLLAMA_SERVICE}"; then
    sed -i '/\[Service\]/a Environment="OLLAMA_MODELS='"${OLLAMA_MODELS_DIR}"'"' "${OLLAMA_SERVICE}"
    systemctl daemon-reload
fi

mkdir -p "${OLLAMA_MODELS_DIR}"
chown -R ollama:ollama "${OLLAMA_MODELS_DIR}"

systemctl enable ollama &>/dev/null
systemctl daemon-reload
systemctl restart ollama
sleep 5
ok "Ollama running"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Pull models
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 4/10 — Pulling models (this takes a while)"

for model in "${EMBED_MODEL}" "${INFERENCE_MODEL}"; do
    if ollama list 2>/dev/null | grep -q "^${model}"; then
        ok "Model already present: ${model}"
    else
        info "Pulling ${model}..."
        ollama pull "${model}"
        ok "Pulled: ${model}"
    fi
done

# Find the inference model blob for llama-server
MODEL_BLOB=$(find "${OLLAMA_MODELS_DIR}/blobs" -name "sha256-*" -size +500M 2>/dev/null | head -1)
if [[ -z "${MODEL_BLOB}" ]]; then
    die "Could not find model blob in ${OLLAMA_MODELS_DIR}/blobs — did the pull succeed?"
fi
ok "Model blob: ${MODEL_BLOB}"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5 — llama.cpp (compile from source)
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 5/10 — llama.cpp (compile from source — ~15 minutes)"

if [[ -f "${LLAMA_BIN}" ]]; then
    ok "llama-server already compiled: ${LLAMA_BIN}"
else
    if [[ ! -d "${LLAMA_DIR}/.git" ]]; then
        info "Cloning llama.cpp..."
        git clone --quiet https://github.com/ggerganov/llama.cpp "${LLAMA_DIR}"
    fi
    info "Compiling with GGML_NATIVE=ON (ARM NEON optimizations)..."
    cmake -B "${LLAMA_DIR}/build" \
        -DGGML_NATIVE=ON \
        -DCMAKE_BUILD_TYPE=Release \
        -S "${LLAMA_DIR}" \
        -Wno-dev > /dev/null 2>&1
    cmake --build "${LLAMA_DIR}/build" \
        --config Release -j4 > /dev/null 2>&1
    ok "llama-server compiled → ${LLAMA_BIN}"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6 — llama-server systemd service
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 6/10 — llama-server service"

LLAMA_SERVICE="/etc/systemd/system/llama-server.service"
if [[ ! -f "${LLAMA_SERVICE}" ]]; then
    cat > "${LLAMA_SERVICE}" << EOF
[Unit]
Description=llama.cpp inference server
After=network.target

[Service]
Type=simple
User=pi
ExecStart=${LLAMA_BIN} --model ${MODEL_BLOB} --ctx-size 2048 --threads 8 --port ${LLAMA_PORT} --host 127.0.0.1 --log-disable
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable llama-server
    ok "llama-server service created and enabled"
else
    ok "llama-server service already exists"
fi

systemctl start llama-server
sleep 5
if curl -sf http://127.0.0.1:${LLAMA_PORT}/health > /dev/null; then
    ok "llama-server running on :${LLAMA_PORT}"
else
    warn "llama-server may still be loading — check: systemctl status llama-server"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7 — PocketBase
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 7/10 — PocketBase v${PB_VERSION}"

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
# STEP 8 — Python venv + packages
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 8/10 — Python venv"

if [[ ! -d "${VENV_DIR}/bin" ]]; then
    python3 -m venv "${VENV_DIR}"
    ok "Created venv → ${VENV_DIR}"
else
    ok "Venv already exists"
fi

source "${VENV_DIR}/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet \
    flask \
    chromadb \
    requests \
    pyyaml \
    pdfplumber \
    python-docx \
    openpyxl \
    agentsoul
ok "Python packages installed"
deactivate

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 9 — Copy agent scripts from repo
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 9/10 — Agent scripts"

REPO_RAW="https://raw.githubusercontent.com/Caltongroup/agent-in-a-box/main"

for script in web_ui.py ingest.py onboard_wizard.py; do
    if [[ ! -f "${DATA_DIR}/${script}" ]]; then
        info "Downloading ${script}..."
        curl -fsSL "${REPO_RAW}/${script}" -o "${DATA_DIR}/${script}"
        ok "Downloaded: ${script}"
    else
        ok "Already present: ${script}"
    fi
done

# Patch web_ui.py to use llama-server on correct port
sed -i "s|LLAMA_URL.*=.*\"http://127.0.0.1:8080\"|LLAMA_URL   = \"http://127.0.0.1:${LLAMA_PORT}\"|" "${DATA_DIR}/web_ui.py" 2>/dev/null || true
sed -i 's|MODEL.*=.*"qwen2.5:1.5b"|MODEL        = "qwen2.5:1.5b"|' "${DATA_DIR}/web_ui.py" 2>/dev/null || true
sed -i 's|"model":.*"local"|"model":      MODEL|g' "${DATA_DIR}/web_ui.py" 2>/dev/null || true
sed -i 's|NUM_PREDICT.*=.*120|NUM_PREDICT  = 300|' "${DATA_DIR}/web_ui.py" 2>/dev/null || true
ok "Agent scripts ready"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 10 — Tailscale
# ═══════════════════════════════════════════════════════════════════════════════
info "Step 10/10 — Tailscale"

if command -v tailscale &>/dev/null; then
    ok "Tailscale already installed: $(tailscale version 2>/dev/null | head -1)"
else
    curl -fsSL https://tailscale.com/install.sh | sh
    systemctl enable tailscaled
    ok "Tailscale installed — run 'tailscale up' to authenticate"
fi

# ── Permissions ───────────────────────────────────────────────────────────────
chown -R pi:pi "${DATA_DIR}"
ok "Ownership set: pi:pi on ${DATA_DIR}"

# ── Summary ───────────────────────────────────────────────────────────────────
PI_IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       Stack deploy complete ✓            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  NVMe mounted    : ${CYAN}${DATA_DIR}${NC}"
echo -e "  llama-server    : ${CYAN}http://127.0.0.1:${LLAMA_PORT}${NC}"
echo -e "  PocketBase      : ${CYAN}http://${PI_IP}:8090/_${NC}"
echo -e "  Python venv     : ${CYAN}${VENV_DIR}${NC}"
echo -e "  Agents home     : ${CYAN}${AGENTS_DIR}${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. Run the onboarding wizard:"
echo -e "     ${CYAN}cd ${DATA_DIR} && source venv/bin/activate && python3 onboard_wizard.py${NC}"
echo -e "  2. Authenticate Tailscale:"
echo -e "     ${CYAN}tailscale up${NC}"
echo ""
