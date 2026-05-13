# Penelope Golden Image — Monday Build Instructions
# Decision ID: d3a11098-1cf6-444f-8293-7462a6e9e3cc
# Free space required: 20 GB minimum (74 GB available — confirmed)

---

## BEFORE YOU START

Make sure the 128 GB SD card is inserted and the Pi is OFF.

---

## STEP 1 — Identify the card

Run BEFORE inserting the card, then AFTER. The new disk is your target.

```bash
diskutil list
```

Look for the ~128 GB disk — typically /dev/disk4 or /dev/disk5.
**Do not guess. Confirm it.**

---

## STEP 2 — Unmount (do NOT eject)

```bash
diskutil unmountDisk /dev/disk4
```

Replace disk4 with your actual disk number.

---

## STEP 3 — Flash Pi OS to the card

Use Raspberry Pi Imager or:

```bash
sudo dd if=path/to/raspios.img of=/dev/disk4 bs=4M
sync
```

---

## STEP 4 — Boot Pi, install all software

Boot the Pi. Run the full setup:
- Ollama + phi3.5 + nomic-embed-text
- PocketBase
- Python venv + packages (requests, chromadb, pypdf, python-docx, openpyxl)
- Copy GoldenImage_Files contents to /home/pi/

---

## STEP 5 — Run validation checks ON THE PI

```bash
python3 ~/golden_boot_check.py
python3 ~/golden_persistence.py
python3 ~/onboard_wizard.py
sudo bash ~/systemd/install_services.sh
python3 ~/penelope_demo_test.py
```

All must exit green before imaging.

---

## STEP 6 — Image the card back to Mac (compressed)

Unmount the card again:
```bash
diskutil unmountDisk /dev/disk4
```

Create the compressed golden image:
```bash
sudo dd if=/dev/disk4 bs=4M | gzip > ~/GoldenImage_Files/golden_image.img.gz
```

**This will take 20-40 minutes. It runs silently.**
To check progress, open a second terminal and run:
```bash
sudo killall -INFO dd
```

---

## STEP 7 — Verify the image

```bash
ls -lh ~/GoldenImage_Files/golden_image.img.gz
```

Expected size: 8-15 GB.
If under 3 GB — something went wrong. Do not use it.

---

## TO RESTORE to a new card later

```bash
diskutil unmountDisk /dev/disk4
gunzip -c ~/GoldenImage_Files/golden_image.img.gz | sudo dd of=/dev/disk4 bs=4M
sync
```

---

## PRE-DEMO CHECK (run morning of every demo)

```bash
python3 ~/penelope_demo_test.py
```

Exit 0 = green. Exit 1 = do not demo blind.

---

*Penelope: Agent in a Box | Built April 5-8, 2026*
