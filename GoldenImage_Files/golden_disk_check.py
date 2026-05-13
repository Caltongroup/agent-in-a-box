#!/usr/bin/env python3
# =============================================================================
# golden_disk_check.py — Penelope: Agent in a Box
# Pre-build disk validation. Run BEFORE flashing the 128 GB golden image.
# Confirms the target card is the right size, healthy, and ready to write.
#
# Usage:
#   python3 golden_disk_check.py              # auto-detects removable disks
#   python3 golden_disk_check.py --dev /dev/sda  # check specific device
# =============================================================================

import sys, os, argparse, subprocess, shutil
from pathlib import Path

REQUIRED_GB   = 128
GB            = 1_073_741_824   # bytes
TOLERANCE_PCT = 10              # accept anything within 10% of 128 GB

PASS  = "  ✓  PASS"
FAIL  = "  ✗  FAIL"
WARN  = "  ⚠  WARN"
INFO  = "  →  INFO"

results = []

def check(label, passed, detail="", warn_only=False):
    tag = PASS if passed else (WARN if warn_only else FAIL)
    line = f"{tag}  {label}"
    if detail:
        line += f"\n           {detail}"
    print(line)
    results.append((label, passed, warn_only))

def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except Exception as e:
        return "", str(e), 1

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_root():
    check("Running as root (required for disk inspection)",
          os.geteuid() == 0,
          "Re-run with: sudo python3 golden_disk_check.py")

def check_platform():
    out, _, _ = run("uname -m")
    is_arm = "aarch64" in out or "armv" in out
    check("ARM architecture detected (Pi target)",
          is_arm, f"uname -m = {out}", warn_only=not is_arm)

def find_removable_disks():
    """Return list of (device, size_bytes, model) for removable block devices."""
    disks = []
    try:
        out, _, _ = run("lsblk -b -d -o NAME,SIZE,RM,MODEL --json")
        import json
        data = json.loads(out)
        for dev in data.get("blockdevices", []):
            if str(dev.get("rm", "0")) == "1":
                disks.append((
                    f"/dev/{dev['name']}",
                    int(dev.get("size", 0)),
                    dev.get("model", "unknown").strip(),
                ))
    except Exception:
        pass
    return disks

def check_disk_size(dev):
    out, _, rc = run(f"blockdev --getsize64 {dev}")
    if rc != 0:
        check("Disk size readable", False, f"Could not read size of {dev}")
        return 0
    size = int(out)
    size_gb = size / GB
    min_gb  = REQUIRED_GB * (1 - TOLERANCE_PCT / 100)
    max_gb  = REQUIRED_GB * (1 + TOLERANCE_PCT / 100)
    ok = min_gb <= size_gb <= max_gb
    check(f"Disk size is ~{REQUIRED_GB} GB",
          ok, f"Actual: {size_gb:.1f} GB  (accepted range: {min_gb:.0f}–{max_gb:.0f} GB)")
    return size

def check_disk_not_mounted(dev):
    out, _, _ = run(f"mount | grep {dev}")
    mounted = bool(out.strip())
    check("Disk is not mounted (safe to write)",
          not mounted,
          f"Mounted partitions found:\n           {out}" if mounted else "")

def check_no_stalled_dd():
    out, _, _ = run("pgrep -a dd")
    stalled = bool(out.strip())
    check("No stalled dd processes running",
          not stalled,
          f"Found: {out}" if stalled else "", warn_only=stalled)

def check_free_space_for_image():
    """Ensure /home/pi (or wherever the image is staged) has room."""
    stage_dir = Path.home()
    usage = shutil.disk_usage(stage_dir)
    free_gb = usage.free / GB
    needed  = REQUIRED_GB * 1.1   # 10% buffer
    ok = free_gb >= needed
    check(f"Enough local free space to stage image ({needed:.0f} GB needed)",
          ok, f"Free: {free_gb:.1f} GB on {stage_dir}", warn_only=not ok)

def check_required_tools():
    tools = ["dd", "lsblk", "blockdev", "sync"]
    for tool in tools:
        found = shutil.which(tool) is not None
        check(f"Tool available: {tool}", found)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Pre-build disk check for Penelope golden image")
    parser.add_argument("--dev", help="Target block device (e.g. /dev/sda). Auto-detected if omitted.")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  Penelope Golden Image — Pre-Build Disk Check")
    print("="*60 + "\n")

    check_root()
    check_platform()
    check_no_stalled_dd()
    check_required_tools()
    check_free_space_for_image()

    dev = args.dev
    if not dev:
        disks = find_removable_disks()
        if not disks:
            print(f"\n{WARN}  No removable disks detected. Insert SD card and retry,")
            print(       "           or specify with: --dev /dev/sdX\n")
        else:
            print(f"\n{INFO}  Removable disk(s) detected:")
            for d, sz, model in disks:
                print(f"           {d}  {sz/GB:.1f} GB  [{model}]")
            dev, size, model = disks[0]
            print(f"\n{INFO}  Checking: {dev} ({model})\n")
            check_disk_size(dev)
            check_disk_not_mounted(dev)
    else:
        check_disk_size(dev)
        check_disk_not_mounted(dev)

    # Summary
    failures = [r for r in results if not r[1] and not r[2]]
    warnings = [r for r in results if not r[1] and r[2]]
    passed   = [r for r in results if r[1]]

    print("\n" + "="*60)
    print(f"  Results: {len(passed)} passed  |  {len(warnings)} warnings  |  {len(failures)} failures")
    print("="*60)

    if failures:
        print("\n  ✗  NOT READY — resolve failures before flashing.\n")
        sys.exit(1)
    elif warnings:
        print("\n  ⚠  READY WITH WARNINGS — review before proceeding.\n")
    else:
        print("\n  ✓  ALL CLEAR — safe to flash golden image.\n")

if __name__ == "__main__":
    main()
