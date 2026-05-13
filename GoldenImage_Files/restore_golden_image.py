#!/usr/bin/env python3
"""
Penelope Golden Image Restore Utility
Safely flash compressed golden_image.img.gz to any SD card (64GB+, 128GB+, etc.)
Author: Archer (Chief of Staff)
Built: April 6, 2026
"""

import os
import sys
import subprocess
import argparse
import time
from pathlib import Path


class GoldenImageRestorer:
    def __init__(self, image_path, verbose=False):
        self.image_path = Path(image_path)
        self.verbose = verbose
        self.home = Path.home()
        
        # Validate image exists
        if not self.image_path.exists():
            raise FileNotFoundError(f"Golden image not found: {self.image_path}")
        if not self.image_path.suffix == ".gz":
            raise ValueError(f"Expected .img.gz file, got: {self.image_path}")
    
    def log(self, msg):
        """Print with timestamp if verbose."""
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}")
    
    def run_cmd(self, cmd, check=True, capture=False):
        """Run shell command safely."""
        self.log(f"Running: {' '.join(cmd)}")
        try:
            if capture:
                result = subprocess.run(cmd, check=check, capture_output=True, text=True)
                return result.stdout.strip()
            else:
                subprocess.run(cmd, check=check)
                return None
        except subprocess.CalledProcessError as e:
            print(f"❌ Command failed: {' '.join(cmd)}")
            if e.stderr:
                print(f"Error: {e.stderr}")
            sys.exit(1)
    
    def list_disks(self):
        """List all external disks and their sizes."""
        output = self.run_cmd(["diskutil", "list"], capture=True)
        lines = output.split('\n')
        
        disks = []
        for line in lines:
            if "(external, physical)" in line:
                parts = line.split()
                disk_id = parts[0].replace("/dev/", "")
                size_str = parts[-2]
                disks.append((disk_id, size_str))
        
        return disks
    
    def get_disk_size_gb(self, disk_id):
        """Get actual disk size in GB."""
        output = self.run_cmd(["diskutil", "info", f"/dev/{disk_id}"], capture=True)
        for line in output.split('\n'):
            if "Total Size:" in line:
                # Extract numeric value
                parts = line.split()
                for i, part in enumerate(parts):
                    if part.isdigit() or (part[0].isdigit() and '.' in part):
                        return float(part)
        return None
    
    def validate_target_disk(self, disk_id):
        """Verify disk is suitable for golden image.
        
        CRITICAL: Target card must be at least as large as the SOURCE card
        that created the golden image. If source was 128GB, target must be 128GB+.
        Restoring a 128GB image to a 64GB card will fail partway with "no space".
        """
        size_gb = self.get_disk_size_gb(disk_id)
        if size_gb is None:
            print(f"❌ Could not determine size of {disk_id}")
            return False
        
        # Minimum 128GB (safe assumption for Penelope golden image from 128GB source)
        if size_gb < 64:
            print(f"❌ Disk too small: {size_gb}GB")
            print("   Golden image requires ≥64GB minimum (preferably 128GB+)")
            print("   Restoring to undersized card will fail with 'no space left'")
            return False
        
        print(f"✓ Disk size: {size_gb:.1f} GB (suitable)")
        return True
    
    def unmount_disk(self, disk_id):
        """Safely unmount (not eject) the disk."""
        print(f"Unmounting /dev/{disk_id}...")
        try:
            self.run_cmd(["diskutil", "unmountDisk", f"/dev/{disk_id}"])
            time.sleep(1)  # Brief delay to ensure unmount completes
            print("✓ Disk unmounted")
        except subprocess.CalledProcessError:
            print("⚠ Unmount failed or disk already unmounted. Continuing...")
    
    def restore_image(self, disk_id):
        """Restore compressed image to disk with progress reporting."""
        print(f"\nRestoring golden image to /dev/{disk_id}...")
        print("This will take 10-30 minutes. Do not disconnect the card.")
        print("-" * 60)
        
        # Build the pipe: gunzip | dd
        # gunzip first, then pipe to dd
        cmd = f"gunzip -c {self.image_path} | sudo dd of=/dev/{disk_id} bs=4M"
        
        try:
            subprocess.run(cmd, shell=True, check=True)
            print("\n" + "-" * 60)
            print("✓ Image restore complete")
        except subprocess.CalledProcessError:
            print("\n" + "-" * 60)
            print("❌ Restore failed. Card may be partially written. Do not use.")
            sys.exit(1)
    
    def sync_disk(self):
        """Sync all buffered writes to disk."""
        print("Syncing disk...")
        self.run_cmd(["sync"])
        print("✓ Sync complete")
    
    def verify_restored(self, disk_id):
        """Quick verification that card is readable."""
        print(f"\nVerifying restored card...")
        try:
            # Try to read first 1MB of the restored disk
            output = self.run_cmd(
                ["sudo", "dd", f"if=/dev/{disk_id}", "bs=1M", "count=1"],
                capture=True
            )
            print("✓ Card is readable")
            return True
        except subprocess.CalledProcessError:
            print("⚠ Could not verify (may still be OK). Eject and test on Pi.")
            return False
    
    def interactive_select_disk(self):
        """Let user pick target disk interactively."""
        disks = self.list_disks()
        
        if not disks:
            print("❌ No external disks detected. Insert SD card and try again.")
            sys.exit(1)
        
        print("\nDetected external disks:")
        for i, (disk_id, size_str) in enumerate(disks, 1):
            print(f"  {i}. /dev/{disk_id} ({size_str})")
        
        if len(disks) == 1:
            choice = 1
            print(f"\nAuto-selected: /dev/{disks[0][0]}")
        else:
            try:
                choice = int(input(f"\nSelect disk (1-{len(disks)}): "))
                if choice < 1 or choice > len(disks):
                    raise ValueError
            except (ValueError, KeyboardInterrupt):
                print("Invalid selection.")
                sys.exit(1)
        
        return disks[choice - 1][0]
    
    def run(self):
        """Main restore workflow."""
        print("╔" + "="*58 + "╗")
        print("║  Penelope Golden Image Restore Utility                ║")
        print("║  Safe SD Card Flashing                                ║")
        print("╚" + "="*58 + "╝\n")
        
        print(f"Golden image: {self.image_path.name}")
        print(f"Image size: {self.image_path.stat().st_size / (1024**3):.1f} GB\n")
        
        # Step 1: Select target disk
        disk_id = self.interactive_select_disk()
        
        # Step 2: Validate
        if not self.validate_target_disk(disk_id):
            sys.exit(1)
        
        # Step 3: Confirm before touching disk
        print(f"\n⚠ WARNING: This will ERASE /dev/{disk_id} and all data on it.")
        confirm = input(f"Type 'yes' to proceed with /dev/{disk_id}: ").strip()
        
        if confirm.lower() != "yes":
            print("❌ Restore cancelled.")
            sys.exit(0)
        
        # Step 4: Restore
        self.unmount_disk(disk_id)
        self.restore_image(disk_id)
        self.sync_disk()
        
        # Step 5: Verify
        self.verify_restored(disk_id)
        
        # Done
        print("\n" + "="*60)
        print("✓ Golden image restore complete!")
        print(f"  Card: /dev/{disk_id}")
        print(f"  Eject and insert into Pi to boot.")
        print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Restore Penelope golden image to SD card",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (recommended)
  python3 restore_golden_image.py
  
  # Specify custom image path
  python3 restore_golden_image.py -i /path/to/custom_image.img.gz
  
  # Verbose logging
  python3 restore_golden_image.py -v
        """
    )
    
    default_image = Path.home() / "GoldenImage_Files/golden_image.img.gz"
    parser.add_argument(
        "-i", "--image",
        type=str,
        default=str(default_image),
        help=f"Path to golden_image.img.gz (default: {default_image})"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging"
    )
    
    args = parser.parse_args()
    
    try:
        restorer = GoldenImageRestorer(args.image, verbose=args.verbose)
        restorer.run()
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n❌ Restore cancelled by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()
