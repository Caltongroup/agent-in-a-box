#!/usr/bin/env python3
# =============================================================================
# golden_boot_check.py — Penelope: Agent in a Box
# Post-boot validation. Run after first boot of a freshly flashed Pi.
# Confirms every component of the golden image is present and functional.
#
# Usage:
#   python3 golden_boot_check.py
#
# Exit code 0 = all required checks passed (safe to run onboard_wizard.py)
# Exit code 1 = one or more required checks failed
# =============================================================================

import sys, os, shutil, subprocess, importlib
from pathlib import Path

HOME = Path("/home/pi")

PASS = "  ✓  PASS"
FAIL = "  ✗  FAIL"
WARN = "  ⚠  WARN"

results = []

def check(label, passed, detail="", warn_only=False):
    tag = PASS if passed else (WARN if warn_only else FAIL)
    line = f"{tag}  {label}"
    if detail:
        line += f"\n           {detail}"
    print(line)
    results.append((label, passed, warn_only))
    return passed

def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", 1
    except Exception as e:
        return "", str(e), 1

# ---------------------------------------------------------------------------
# Filesystem checks
# ---------------------------------------------------------------------------
def check_filesystem():
    print("\n  [ Filesystem & Paths ]\n")

    paths = {
        "Python venv":            HOME / "venv",
        "venv Python binary":     HOME / "venv/bin/python",
        "PocketBase binary":      HOME / "pocketbase/pocketbase",
        "PocketBase data dir":    HOME / "pocketbase/data",
        "Hermes skeleton":        HOME / "hermes",
        "Hermes main.py":         HOME / "hermes/main.py",
        "Hermes gateway.py":      HOME / "hermes/gateway.py",
        "onboard_wizard.py":      HOME / "onboard_wizard.py",
        "ingest.py":              HOME / "ingest.py",
        "watcher.py":             HOME / "watcher.py",
    }
    for label, path in paths.items():
        exists = path.exists()
        check(f"{label}: {path}", exists,
              warn_only=("gateway" in str(path) or "hermes/main" in str(path)))

def check_disk_space():
    print("\n  [ Disk Space ]\n")
    import shutil as sh
    usage = sh.disk_usage("/")
    free_gb = usage.free / 1_073_741_824
    total_gb = usage.total / 1_073_741_824
    check(f"Root filesystem: {free_gb:.1f} GB free of {total_gb:.1f} GB",
          free_gb >= 10,
          f"Warning: less than 10 GB free — may not have room for documents/models",
          warn_only=free_gb < 10)

# ---------------------------------------------------------------------------
# Python environment checks
# ---------------------------------------------------------------------------
def check_python():
    print("\n  [ Python Environment ]\n")

    # Python version
    out, _, _ = run(f"{HOME}/venv/bin/python --version")
    ok = "3." in out
    check(f"Python 3 in venv: {out}", ok)

    # Required packages
    packages = {
        "requests":  "requests",
        "chromadb":  "chromadb",
        "pypdf":     "pypdf",
        "python-docx": "docx",
        "openpyxl":  "openpyxl",
    }
    for pkg_name, import_name in packages.items():
        out, _, rc = run(
            f"{HOME}/venv/bin/python -c 'import {import_name}' 2>&1"
        )
        check(f"Python package: {pkg_name}", rc == 0, warn_only=True)

# ---------------------------------------------------------------------------
# Service checks
# ---------------------------------------------------------------------------
def check_ollama():
    print("\n  [ Ollama & Models ]\n")

    # Ollama running
    out, _, rc = run("curl -sf http://localhost:11434/api/tags", timeout=5)
    running = rc == 0
    check("Ollama service running", running,
          "Start with: ollama serve &")

    if running:
        # Phi-3.5-mini
        phi_ok = "phi3.5" in out or "phi-3.5" in out.lower()
        check("Model: phi3.5 (Phi-3.5-mini) pulled",
              phi_ok, "Pull with: ollama pull phi3.5")

        # nomic-embed-text
        nomic_ok = "nomic-embed-text" in out
        check("Model: nomic-embed-text pulled",
              nomic_ok, "Pull with: ollama pull nomic-embed-text")

def check_pocketbase():
    print("\n  [ PocketBase ]\n")

    binary = HOME / "pocketbase/pocketbase"
    check("PocketBase binary exists", binary.exists())

    if binary.exists():
        out, _, rc = run(f"{binary} --version", timeout=5)
        check(f"PocketBase binary executable: {out}", rc == 0)

    # Check if already running
    out, _, rc = run("curl -sf http://127.0.0.1:8090/api/health", timeout=3)
    check("PocketBase health check", rc == 0,
          "Not required at boot — starts via systemd or onboard_wizard.py",
          warn_only=True)

def check_systemd():
    print("\n  [ Systemd Services ]\n")

    services = ["pocketbase", "hermes-agent", "hermes-gateway"]
    for svc in services:
        out, _, rc = run(f"systemctl is-enabled {svc} 2>/dev/null")
        enabled = "enabled" in out
        check(f"systemd service enabled: {svc}", enabled,
              f"Enable with: sudo systemctl enable {svc}",
              warn_only=True)

# ---------------------------------------------------------------------------
# Network check
# ---------------------------------------------------------------------------
def check_network():
    print("\n  [ Network ]\n")
    out, _, rc = run("curl -sf --max-time 5 https://1.1.1.1", timeout=8)
    check("Internet connectivity", rc == 0,
          "Needed for first-run pip installs if packages are missing",
          warn_only=True)

    # Local hostname
    out, _, _ = run("hostname -I")
    check(f"Local IP assigned: {out}", bool(out.strip()))

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("\n" + "="*60)
    print("  Penelope Golden Image — Post-Boot Validation")
    print("="*60)

    check_filesystem()
    check_disk_space()
    check_python()
    check_ollama()
    check_pocketbase()
    check_systemd()
    check_network()

    # Summary
    failures = [r for r in results if not r[1] and not r[2]]
    warnings = [r for r in results if not r[1] and r[2]]
    passed   = [r for r in results if r[1]]

    print("\n" + "="*60)
    print(f"  Results: {len(passed)} passed  |  {len(warnings)} warnings  |  {len(failures)} failures")
    print("="*60)

    if failures:
        print("\n  ✗  IMAGE NOT READY — fix failures before running onboard_wizard.py\n")
        for label, _, _ in failures:
            print(f"       → {label}")
        print()
        sys.exit(1)
    elif warnings:
        print("\n  ⚠  READY WITH WARNINGS — review above, then run: python3 onboard_wizard.py\n")
    else:
        print("\n  ✓  ALL SYSTEMS GO — run: python3 ~/onboard_wizard.py\n")

if __name__ == "__main__":
    main()
