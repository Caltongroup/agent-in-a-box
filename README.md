# Agent in a Box

A self-contained local AI agent that runs on an Orange Pi 5 Pro (or any ARM64 Linux board). Fully private — no cloud, no subscriptions. Configurable for any business vertical in minutes.

---

## Hardware

| Component | Spec |
|-----------|------|
| Board | Orange Pi 5 Pro (RK3588S, 16 GB RAM) |
| OS | Armbian Trixie (ARM64) |
| Storage | NVMe SSD (128 GB+) mounted at `/home/pi/data` |
| Network | Ethernet + Tailscale for remote access |

---

## What Gets Installed

| Component | Purpose |
|-----------|---------|
| llama.cpp | Local inference server (port 8080) |
| qwen2.5:1.5b | Default inference model (~1 GB) |
| Ollama | Embeddings only (nomic-embed-text) |
| ChromaDB | Local RAG vector store |
| PocketBase | Session logging and memory (port 8090) |
| Flask | Web chat UI (port 5000 by default) |
| Tailscale | Secure remote access |

---

## First-Time Setup (new box)

### Step 1 — Flash and boot
1. Download Armbian Trixie for Orange Pi 5 Pro
2. Flash to SD card, boot, complete initial setup (set `pi` user password)
3. SSH in: `ssh pi@<ip>`

### Step 2 — Deploy the stack
```bash
curl -fsSL https://raw.githubusercontent.com/Caltongroup/agent-in-a-box/main/deploy_stack.sh -o deploy_stack.sh
sudo bash deploy_stack.sh
```

This takes 15–25 minutes. It will:
- Mount and format the NVMe SSD
- Install and configure Ollama (embeddings only)
- Pull qwen2.5:1.5b and nomic-embed-text models
- Compile llama.cpp from source with ARM NEON optimisations
- Create llama-server systemd service
- Install PocketBase
- Create Python venv with all dependencies
- Download web_ui.py, ingest.py, and onboard_wizard.py from this repo
- Install Tailscale

### Step 3 — Run the onboarding wizard
```bash
cd /home/pi/data
source venv/bin/activate
python3 onboard_wizard.py
```

The wizard asks:
- Business / organisation name
- Industry / vertical (HR, Radio Station, Senior Care, Retail, etc.)
- One-sentence purpose of the agent
- GitHub repo URL for documents (optional — can skip and add files manually)
- Web UI port (default: 5000)
- Key contacts (name, email, role)

It then:
- Creates `/home/pi/data/agents/{name}_agent/` with SOUL.md, documents/, chroma_db/
- Clones the document repo and builds the RAG vector store (if repo provided)
- Creates and starts a systemd service for the web UI
- Seeds contacts into PocketBase

### Step 4 — Authenticate Tailscale
```bash
sudo tailscale up
```
Follow the link to authenticate. The box will then be reachable from anywhere on your Tailnet.

### Step 5 — Open the agent
```
http://<pi-ip>:5000
```

---

## Adding or Updating Documents

Drop files into `/home/pi/data/agents/{name}_agent/documents/` then re-run ingest:

```bash
cd /home/pi/data
source venv/bin/activate
python3 ingest.py \
  --chroma-db /home/pi/data/agents/{name}_agent/chroma_db \
  --collection {name} \
  --docs /home/pi/data/agents/{name}_agent/documents
```

Supported formats: `.pdf`, `.docx`, `.txt`, `.md`, `.xlsx`, `.csv`

To rebuild from scratch (drop all old vectors):
```bash
python3 ingest.py ... --fresh
```

---

## Managing Services

| Action | Command |
|--------|---------|
| Check agent status | `sudo systemctl status {name}-agent` |
| Restart agent | `sudo systemctl restart {name}-agent` |
| Check llama-server | `sudo systemctl status llama-server` |
| Check PocketBase | `sudo systemctl status pocketbase` |
| View agent logs | `sudo journalctl -u {name}-agent -f` |
| View llama logs | `sudo journalctl -u llama-server -f` |

---

## PocketBase Admin

PocketBase stores session logs and contacts.

- UI: `http://<pi-ip>:8090/_`
- Create admin credentials on first visit
- Save them to `~/.pb_admin_creds` for the wizard to use:

```bash
cat > ~/.pb_admin_creds << 'EOF'
{"email":"admin@example.com","password":"yourpassword"}
EOF
```

---

## Per-Customer Document Repos

Each customer gets a private GitHub repo containing their documents. The onboarding wizard clones it automatically.

Naming convention: `Caltongroup/{customer-slug}-agent`

Example:
```
Caltongroup/iliad-hr-agent/
  policies/
  handbooks/
  onboarding/
```

To update documents after the initial setup:
```bash
cd /home/pi/data/agents/{name}_agent/documents
git pull
python3 /home/pi/data/ingest.py --chroma-db ../chroma_db --collection {name} --docs .
sudo systemctl restart {name}-agent
```

---

## File Layout on the SSD

```
/home/pi/data/
├── venv/                  Python virtual environment
├── llama.cpp/             llama.cpp source + compiled binaries
├── ollama/                Ollama model storage
├── pocketbase/            PocketBase binary + data
├── agents/
│   └── {name}_agent/
│       ├── SOUL.md        Agent identity and personality
│       ├── documents/     Source documents for RAG
│       ├── chroma_db/     ChromaDB vector store
│       └── start_agent.sh Manual launch fallback
├── web_ui.py              Flask streaming chat interface
├── ingest.py              Document ingestion + RAG builder
└── onboard_wizard.py      First-boot configuration wizard
```

---

## Troubleshooting

**Agent not responding**
```bash
sudo systemctl status {name}-agent
curl -s http://127.0.0.1:8080/health   # llama-server health check
```

**Slow responses (~30–40s)**
Normal for qwen2.5:1.5b on CPU. Ensure llama-server is running (not Ollama) for inference.

**RAG returning no results**
Re-run ingest.py. Check chunk count in ChromaDB collection matches number of documents ingested.

**Cannot reach box on company network**
Use Tailscale: `ssh pi@$(tailscale ip -4)` or `http://$(tailscale ip -4):5000`

**HDMI not working**
Plug monitor in before powering on. Hot-plug does not work on Orange Pi 5 Pro.

**Bracketed paste in terminal**
```bash
bind 'set enable-bracketed-paste off'
```

---

## Useful Commands

```bash
# SSH into the box
ssh pi@<ip>

# Shut down safely
sudo shutdown now

# Check what's running
sudo systemctl list-units --state=running | grep -E "llama|pocketbase|agent"

# Check SSD usage
df -h /home/pi/data

# Check model files
ollama list

# Test llama-server directly
curl -s http://127.0.0.1:8080/health
```

---

## Repo Structure

```
agent-in-a-box/
├── deploy_stack.sh      Full stack deployer — run once on a fresh box
├── onboard_wizard.py    Vertical configuration wizard
├── web_ui.py            Flask streaming chat UI
├── ingest.py            Document ingestion for RAG
└── README.md            This file
```

---

## Architecture

```
User browser
     │
     ▼
Flask web UI (port 5000)
     │
     ├── ChromaDB (RAG retrieval) ◄── documents/
     │
     ├── llama.cpp server (port 8080) ◄── qwen2.5:1.5b
     │
     ├── Ollama (port 11434) ◄── nomic-embed-text
     │
     └── PocketBase (port 8090) ◄── session logs
```

All components run locally. No data leaves the box.
