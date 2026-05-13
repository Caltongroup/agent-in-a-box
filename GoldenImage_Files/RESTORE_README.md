# Restore Golden Image to SD Card

Quick reference for flashing the Penelope golden image to new cards.

## Quick Start

```bash
python3 restore_golden_image.py
```

Script will:
1. **List** all connected external disks
2. **Auto-select** if only one (or prompt you)
3. **Validate** card size (≥10GB)
4. **Confirm** before erasing
5. **Restore** image with progress
6. **Verify** the card is readable

## Requirements

- **Target SD card: ≥64GB minimum (128GB+ recommended)**
  - ⚠️ CRITICAL: Source card size = minimum target card size
  - If golden image was created from 128GB card, target must be 128GB+
  - Restoring to undersized card will fail with "no space left on device" (partial write, card unusable)
- macOS with `diskutil`, `dd`, `gunzip` (all standard)
- `sudo` access (will prompt for password)
- Golden image: `~/GoldenImage_Files/golden_image.img.gz`

## Options

```bash
# Specify custom image location
python3 restore_golden_image.py -i /path/to/custom.img.gz

# Verbose logging
python3 restore_golden_image.py -v

# Both
python3 restore_golden_image.py -i /path/to/image.img.gz -v
```

## What It Does

1. **Detects** all external disks
2. **Validates** target card size (must be ≥10GB for golden image)
3. **Unmounts** (safely, without ejecting)
4. **Restores** by piping `gunzip | dd` (standard, battle-tested)
5. **Syncs** writes to disk
6. **Verifies** card is readable

## Safety Features

- ✓ **Size validation** (rejects cards smaller than source golden image)
- ✓ **Explicit confirmation** before erasing
- ✓ **Progress feedback** during restore
- ✓ **Read verification** after restore
- ✓ **Error handling** with clear exit codes

## Time Estimates

- Restore (gunzip + dd): **10-30 minutes** (depends on card speed)
- Full process: **15-35 minutes**

## After Restore

1. Eject the card from Mac
2. Insert into Pi
3. Boot Pi and verify Penelope starts
4. Run `python3 ~/penelope_demo_test.py` to confirm all systems

## Troubleshooting

**"Golden image not found"**
- Check that `~/GoldenImage_Files/golden_image.img.gz` exists
- Or use `-i /path/to/image` to specify custom location

**"Disk too small"**
- Card must be ≥64GB minimum
- Script rejects undersized cards to prevent partial write failures
- If golden image was created from 128GB, target must be 128GB+
- 64GB card can be used for scripts/code backup only (not bootable restore)

**"Restore failed"**
- Card may be corrupted
- Try a different card
- Restore process is idempotent — safe to retry

**"Could not verify"**
- Usually OK — card may still be good
- Test on Pi to confirm

---

**Built by Archer | April 6, 2026**
