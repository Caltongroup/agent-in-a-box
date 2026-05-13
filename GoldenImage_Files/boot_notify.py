#!/usr/bin/env python3
# =============================================================================
# boot_notify.py — Penelope: Agent in a Box
# Sends a Telegram message when Penelope boots and all services are healthy.
# Called by a systemd oneshot service (penelope-notify.service) that runs
# after all other services are up.
#
# Also sends an alert if any required service is DOWN.
#
# Usage:
#   python3 boot_notify.py --token <BOT_TOKEN> --chat-id <CHAT_ID>
#
# Get your chat ID: message your bot, then:
#   curl https://api.telegram.org/bot<TOKEN>/getUpdates
# =============================================================================

import sys, argparse, subprocess, socket, time
from pathlib import Path

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "-q", "--break-system-packages"])
    import requests

PB_URL     = "http://127.0.0.1:8090"
OLLAMA_URL = "http://localhost:11434"
HOME       = Path("/home/pi")

# ---------------------------------------------------------------------------
# Health checks (lightweight — just ping, no writes)
# ---------------------------------------------------------------------------
def service_ok(url, timeout=3):
    try:
        return requests.get(url, timeout=timeout).status_code == 200
    except Exception:
        return False

def get_ip():
    try:
        return subprocess.check_output(
            "hostname -I | awk '{print $1}'", shell=True, text=True
        ).strip()
    except Exception:
        return "unknown"

def get_tailscale_ip():
    try:
        out = subprocess.check_output(
            "tailscale ip -4 2>/dev/null", shell=True, text=True
        ).strip()
        return out if out else None
    except Exception:
        return None

def get_project_name():
    candidates = sorted(HOME.glob("*_agent"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0].name.replace("_agent", "").replace("_", " ").title()
    return "Unknown"

def get_soul_name(project_name):
    candidates = sorted(HOME.glob("*_agent"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        soul = candidates[0] / "SOUL.md"
        if soul.exists():
            for line in soul.read_text().splitlines():
                if line.startswith("- **Name:**"):
                    return line.split("**Name:**")[-1].strip()
    return "Penelope"

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "Markdown",
    }, timeout=10)
    return r.status_code == 200

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Send Telegram boot notification for Penelope"
    )
    parser.add_argument("--token",   required=True, help="Telegram bot token")
    parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    parser.add_argument("--wait",    type=int, default=15,
                        help="Seconds to wait for services before notifying (default 15)")
    args = parser.parse_args()

    # Brief wait to let services settle after boot
    time.sleep(args.wait)

    pb_up     = service_ok(f"{PB_URL}/api/health")
    ollama_up = service_ok(f"{OLLAMA_URL}/api/tags", timeout=5)
    local_ip  = get_ip()
    ts_ip     = get_tailscale_ip()
    project   = get_project_name()
    agent     = get_soul_name(project)
    hostname  = socket.gethostname()

    all_ok = pb_up and ollama_up

    if all_ok:
        status_line = "✅ *All systems operational*"
        services = (
            f"  • PocketBase: ✅\n"
            f"  • Ollama: ✅\n"
        )
    else:
        status_line = "⚠️ *Boot complete — service issues detected*"
        services = (
            f"  • PocketBase: {'✅' if pb_up else '❌'}\n"
            f"  • Ollama: {'✅' if ollama_up else '❌'}\n"
        )

    network = f"  • LAN: `{local_ip}`\n"
    if ts_ip:
        network += f"  • Tailscale: `{ts_ip}`\n"
    else:
        network += f"  • Tailscale: ⚠️ not connected\n"

    message = (
        f"🤖 *{agent}* is online\n"
        f"_{project} · {hostname}_\n\n"
        f"{status_line}\n\n"
        f"*Services:*\n{services}\n"
        f"*Network:*\n{network}\n"
        f"*Dashboard:* http://{local_ip}:8090/_/\n"
        f"_Penelope: Agent in a Box_"
    )

    ok = send_telegram(args.token, args.chat_id, message)
    if ok:
        print(f"  ✓  Boot notification sent to chat {args.chat_id}")
    else:
        print(f"  ⚠  Failed to send Telegram notification", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
