#!/usr/bin/env python3
# =============================================================================
# golden_persistence.py — Penelope: Agent in a Box
# Validates the full persistence layer end-to-end.
# Confirms PocketBase starts, accepts reads/writes, and survives a restart.
# Run after golden_boot_check.py passes.
#
# Usage:
#   python3 golden_persistence.py
#   python3 golden_persistence.py --skip-restart   # skip the restart test
# =============================================================================

import sys, time, argparse, subprocess, uuid
from pathlib import Path

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "-q", "--break-system-packages"])
    import requests

HOME   = Path("/home/pi")
PB_BIN = HOME / "pocketbase/pocketbase"
PB_DATA = HOME / "pocketbase/data"
PB_URL  = "http://127.0.0.1:8090"
TEST_COLLECTION = "penelope_persistence_test"

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

# ---------------------------------------------------------------------------
# PocketBase lifecycle
# ---------------------------------------------------------------------------
def pb_start():
    """Start PocketBase if not running. Returns True when healthy."""
    try:
        if requests.get(f"{PB_URL}/api/health", timeout=2).status_code == 200:
            check("PocketBase already running", True)
            return True
    except requests.ConnectionError:
        pass

    print(f"  →  Starting PocketBase…")
    proc = subprocess.Popen(
        [str(PB_BIN), "serve", "--dir", str(PB_DATA)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    for _ in range(15):
        time.sleep(1)
        try:
            if requests.get(f"{PB_URL}/api/health", timeout=2).status_code == 200:
                check("PocketBase started successfully", True)
                return True
        except requests.ConnectionError:
            pass

    check("PocketBase started successfully", False,
          f"Binary: {PB_BIN} | Data: {PB_DATA}\n"
          f"           Check: journalctl -u pocketbase -n 20")
    return False

def pb_stop():
    subprocess.run("pkill -f 'pocketbase serve'", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

def pb_health():
    try:
        return requests.get(f"{PB_URL}/api/health", timeout=3).status_code == 200
    except requests.ConnectionError:
        return False

# ---------------------------------------------------------------------------
# Collection + record operations
# ---------------------------------------------------------------------------
def create_test_collection():
    # Delete if exists (clean slate for test)
    requests.delete(f"{PB_URL}/api/collections/{TEST_COLLECTION}", timeout=5)

    r = requests.post(f"{PB_URL}/api/collections", timeout=5, json={
        "name": TEST_COLLECTION,
        "type": "base",
        "schema": [
            {"name": "value",     "type": "text",    "required": True},
            {"name": "run_id",    "type": "text",     "required": False},
        ]
    })
    ok = r.status_code in (200, 201)
    check("Create test collection", ok,
          r.text[:100] if not ok else "")
    return ok

def write_record(run_id):
    payload = {"value": "penelope_persistence_ok", "run_id": run_id}
    r = requests.post(
        f"{PB_URL}/api/collections/{TEST_COLLECTION}/records",
        json=payload, timeout=5
    )
    ok = r.status_code in (200, 201)
    record_id = r.json().get("id") if ok else None
    check("Write record to PocketBase", ok,
          f"record_id={record_id}" if ok else r.text[:100])
    return record_id

def read_record(record_id):
    r = requests.get(
        f"{PB_URL}/api/collections/{TEST_COLLECTION}/records/{record_id}",
        timeout=5
    )
    ok = r.status_code == 200 and r.json().get("value") == "penelope_persistence_ok"
    check("Read record back from PocketBase", ok,
          r.text[:100] if not ok else "")
    return ok

def query_by_run_id(run_id):
    r = requests.get(
        f"{PB_URL}/api/collections/{TEST_COLLECTION}/records",
        params={"filter": f'run_id="{run_id}"'},
        timeout=5
    )
    ok = r.status_code == 200 and r.json().get("totalItems", 0) > 0
    check("Query records by field filter", ok,
          r.text[:100] if not ok else "")
    return ok

def cleanup_test_collection():
    r = requests.delete(
        f"{PB_URL}/api/collections/{TEST_COLLECTION}", timeout=5
    )
    check("Cleanup test collection", r.status_code in (200, 204), warn_only=True)

# ---------------------------------------------------------------------------
# Restart survival test
# ---------------------------------------------------------------------------
def test_restart_survival(record_id):
    print("\n  [ Restart Survival Test ]\n")
    print("  →  Stopping PocketBase…")
    pb_stop()

    alive = pb_health()
    check("PocketBase stopped cleanly", not alive)

    print("  →  Restarting PocketBase…")
    if not pb_start():
        return

    r = requests.get(
        f"{PB_URL}/api/collections/{TEST_COLLECTION}/records/{record_id}",
        timeout=5
    )
    survived = r.status_code == 200 and \
               r.json().get("value") == "penelope_persistence_ok"
    check("Record survived PocketBase restart", survived,
          "State did NOT persist — check PB_DATA path and disk write permissions"
          if not survived else "")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Validate Penelope persistence layer end-to-end"
    )
    parser.add_argument("--skip-restart", action="store_true",
                        help="Skip the PocketBase restart survival test")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  Penelope Golden Image — Persistence Layer Validation")
    print("="*60)

    run_id = str(uuid.uuid4())[:8]

    print("\n  [ PocketBase Startup ]\n")
    if not pb_start():
        print("\n  ✗  Cannot proceed — PocketBase failed to start.\n")
        sys.exit(1)

    print("\n  [ Collection & Record Operations ]\n")
    if not create_test_collection():
        print("\n  ✗  Cannot proceed — collection creation failed.\n")
        sys.exit(1)

    record_id = write_record(run_id)
    if not record_id:
        sys.exit(1)

    read_record(record_id)
    query_by_run_id(run_id)

    if not args.skip_restart:
        test_restart_survival(record_id)
        # Restart may recreate PB connection — re-check health
        if pb_health():
            cleanup_test_collection()
    else:
        print("\n  [ Restart test skipped (--skip-restart) ]\n")
        cleanup_test_collection()

    # Summary
    failures = [r for r in results if not r[1] and not r[2]]
    warnings = [r for r in results if not r[1] and r[2]]
    passed   = [r for r in results if r[1]]

    print("\n" + "="*60)
    print(f"  Results: {len(passed)} passed  |  {len(warnings)} warnings  |  {len(failures)} failures")
    print("="*60)

    if failures:
        print("\n  ✗  PERSISTENCE NOT READY — backbone is not stable.\n")
        sys.exit(1)
    elif warnings:
        print("\n  ⚠  PERSISTENCE OK WITH WARNINGS\n")
    else:
        print("\n  ✓  PERSISTENCE FULLY VALIDATED — backbone is solid.\n")

if __name__ == "__main__":
    main()
