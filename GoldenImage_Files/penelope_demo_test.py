#!/usr/bin/env python3
# =============================================================================
# penelope_demo_test.py — Penelope: Agent in a Box
# One-command pre-demo validator. Run this the morning of every demo.
# Tests the full stack end-to-end: PocketBase → Ollama → ChromaDB → Hermes.
#
# Usage:
#   python3 penelope_demo_test.py
#   python3 penelope_demo_test.py --project /home/pi/my_org_agent
#
# Exit 0 = all green, safe to demo
# Exit 1 = something is broken, do not demo blind
# =============================================================================

import sys, time, argparse, subprocess
from pathlib import Path

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "-q", "--break-system-packages"])
    import requests

PB_URL     = "http://127.0.0.1:8090"
OLLAMA_URL = "http://localhost:11434"
EMBED      = "nomic-embed-text"
HOME       = Path("/home/pi")

PASS = "  ✓"
FAIL = "  ✗"
WARN = "  ⚠"

results = []

def check(label, passed, detail="", warn_only=False):
    tag = PASS if passed else (WARN if warn_only else FAIL)
    print(f"{tag}  {label}" + (f"\n      → {detail}" if detail else ""))
    results.append((label, passed, warn_only))
    return passed

def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except Exception:
        return "", 1

# ---------------------------------------------------------------------------
# 1. Services
# ---------------------------------------------------------------------------
def check_services():
    print("\n  ── Services ──\n")

    # PocketBase
    try:
        r = requests.get(f"{PB_URL}/api/health", timeout=3)
        check("PocketBase responding", r.status_code == 200)
    except Exception:
        check("PocketBase responding", False, f"curl {PB_URL}/api/health failed")

    # Ollama
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        ok = r.status_code == 200
        check("Ollama responding", ok)
        if ok:
            models = [m["name"] for m in r.json().get("models", [])]
            check("qwen2.5:1.5b model available",
                  any("qwen2.5" in m for m in models),
                  "Run: ollama pull qwen2.5:1.5b")
            check("nomic-embed-text available",
                  any("nomic-embed-text" in m for m in models),
                  "Run: ollama pull nomic-embed-text")
    except Exception:
        check("Ollama responding", False, f"curl {OLLAMA_URL}/api/tags failed")

    # Tailscale
    out, rc = run("tailscale status --json 2>/dev/null | python3 -c "
                  "\"import sys,json; d=json.load(sys.stdin); "
                  "print('up' if d.get('BackendState')=='Running' else 'down')\"",
                  timeout=5)
    check("Tailscale connected", out == "up",
          "Run: sudo tailscale up", warn_only=True)

# ---------------------------------------------------------------------------
# 2. Project folder
# ---------------------------------------------------------------------------
def check_project(project_dir: Path):
    print("\n  ── Project Folder ──\n")
    check("Project folder exists", project_dir.exists(),
          f"Expected: {project_dir}")
    check("SOUL.md present", (project_dir / "SOUL.md").exists())
    check("documents/ folder present", (project_dir / "documents").exists())
    check("chroma_db/ folder present", (project_dir / "chroma_db").exists())

    docs = list((project_dir / "documents").glob("*")) if \
           (project_dir / "documents").exists() else []
    supported = [f for f in docs if f.suffix.lower() in
                 {".pdf", ".docx", ".xlsx", ".txt", ".md", ".csv"}]
    check(f"Documents loaded ({len(supported)} file(s))",
          len(supported) > 0,
          "Drop files into documents/ folder and re-run watcher",
          warn_only=True)

# ---------------------------------------------------------------------------
# 3. Embedding smoke test
# ---------------------------------------------------------------------------
def check_embeddings():
    print("\n  ── Embedding Smoke Test ──\n")
    try:
        r = requests.post(f"{OLLAMA_URL}/api/embeddings",
                          json={"model": EMBED, "prompt": "Penelope demo test"},
                          timeout=30)
        ok = r.status_code == 200 and len(r.json().get("embedding", [])) > 0
        dim = len(r.json().get("embedding", []))
        check(f"nomic-embed-text returns vector (dim={dim})", ok)
    except Exception as e:
        check("nomic-embed-text embedding call", False, str(e))

# ---------------------------------------------------------------------------
# 4. ChromaDB smoke test
# ---------------------------------------------------------------------------
def check_chromadb(project_dir: Path):
    print("\n  ── ChromaDB Smoke Test ──\n")
    chroma_dir = project_dir / "chroma_db"
    if not chroma_dir.exists():
        check("ChromaDB directory present", False); return
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collections = client.list_collections()
        check("ChromaDB opens cleanly", True)
        check(f"Collections present ({len(collections)})",
              len(collections) > 0,
              "Run: python3 ingest.py --docs documents/ ... to index files",
              warn_only=True)
        if collections:
            col = client.get_collection(collections[0].name)
            count = col.count()
            check(f"Indexed chunks in '{collections[0].name}': {count}",
                  count > 0, warn_only=True)
    except ImportError:
        check("chromadb package available", False,
              "Run: pip install chromadb --break-system-packages")
    except Exception as e:
        check("ChromaDB opens cleanly", False, str(e))

# ---------------------------------------------------------------------------
# 5. PocketBase write/read
# ---------------------------------------------------------------------------
def check_persistence():
    print("\n  ── Persistence Smoke Test ──\n")
    try:
        # Authenticate as admin first
        auth_r = requests.post(f"{PB_URL}/api/admins/auth-with-password",
                               json={"identity": "admin2@penelope.local",
                                     "password": "Penelope12345"},
                               timeout=5)
        if auth_r.status_code != 200:
            check("PocketBase write + read", False,
                  f"Admin auth failed: {auth_r.status_code}")
            return
        
        token = auth_r.json().get("token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Quick write + read to sessions collection with auth
        r = requests.post(f"{PB_URL}/api/collections/sessions/records",
                          json={"summary": "demo_test"}, 
                          headers=headers, timeout=5)
        if r.status_code in (200, 201):
            rec_id = r.json().get("id")
            r2 = requests.get(
                f"{PB_URL}/api/collections/sessions/records/{rec_id}", 
                headers=headers, timeout=5)
            check("PocketBase write + read", r2.status_code == 200)
            # Clean up
            requests.delete(
                f"{PB_URL}/api/collections/sessions/records/{rec_id}", 
                headers=headers, timeout=5)
        else:
            check("PocketBase write + read", False,
                  f"Status {r.status_code}: {r.text[:80]}")
    except Exception as e:
        check("PocketBase write + read", False, str(e))

# ---------------------------------------------------------------------------
# 6. Systemd service status
# ---------------------------------------------------------------------------
def check_systemd():
    print("\n  ── Service Health ──\n")
    services = ["pocketbase", "ollama", "watcher",
                "hermes-webui", "hermes-agent", "hermes-gateway"]
    for svc in services:
        out, rc = run(f"systemctl is-active {svc} 2>/dev/null")
        active = out == "active"
        check(f"systemd: {svc} is active", active,
              f"sudo systemctl start {svc}",
              warn_only=svc in ("hermes-agent", "hermes-gateway", "watcher", "hermes-webui"))

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Penelope pre-demo health check")
    parser.add_argument("--project", help="Project folder path",
                        default=None)
    args = parser.parse_args()

    # Auto-detect project folder if not specified
    if args.project:
        project_dir = Path(args.project)
    else:
        candidates = sorted(HOME.glob("*_agent"), key=lambda p: p.stat().st_mtime,
                            reverse=True) if HOME.exists() else []
        project_dir = candidates[0] if candidates else HOME / "my_organization_agent"

    print("\n" + "="*60)
    print("  Penelope — Pre-Demo System Check")
    print(f"  Project: {project_dir}")
    print("="*60)

    check_services()
    check_project(project_dir)
    check_embeddings()
    check_chromadb(project_dir)
    check_persistence()
    check_systemd()

    failures = [r for r in results if not r[1] and not r[2]]
    warnings = [r for r in results if not r[1] and r[2]]
    passed   = [r for r in results if r[1]]

    print("\n" + "="*60)
    print(f"  {len(passed)} passed  |  {len(warnings)} warnings  |  {len(failures)} failures")
    print("="*60)

    if failures:
        print("\n  ✗  DO NOT DEMO — fix failures first:\n")
        for label, _, _ in failures:
            print(f"       → {label}")
        print()
        sys.exit(1)
    elif warnings:
        print("\n  ⚠  DEMO READY WITH WARNINGS — review above.\n")
    else:
        print("\n  ✓  ALL GREEN — Penelope is ready. Go close the deal.\n")

if __name__ == "__main__":
    main()
