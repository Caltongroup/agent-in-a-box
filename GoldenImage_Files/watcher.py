#!/usr/bin/env python3
# =============================================================================
# watcher.py — Generic RAG Folder Watcher
# Agent in a Box | Decision ID: d3a11098-1cf6-444f-8293-7462a6e9e3cc
#
# Polls the documents/ folder on an interval and auto-ingests new or changed
# files using ingest.py. No watchdog dependency — pure polling for maximum
# ARM/Pi 5 compatibility.
#
# Runs as a background daemon alongside the agent. Already wired into
# start_agent.sh via onboard_wizard.py.
#
# Usage:
#   python watcher.py --docs /path/to/documents \
#                     --collection my_business  \
#                     --chroma-dir /path/to/chroma_db \
#                     [--interval 30]
# =============================================================================

import sys, time, hashlib, argparse, signal
from pathlib import Path

# Import ingest functions (same directory)
sys.path.insert(0, str(Path(__file__).parent))
from ingest import ingest_file, ingest_folder, SUPPORTED_EXT

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_INTERVAL = 30  # seconds between polls

# ---------------------------------------------------------------------------
# Watcher
# ---------------------------------------------------------------------------
class FolderWatcher:
    def __init__(self, docs_dir: Path, collection_name: str,
                 chroma_dir: Path, interval: int):
        self.docs_dir        = docs_dir
        self.collection_name = collection_name
        self.chroma_dir      = chroma_dir
        self.interval        = interval
        self.seen_hashes     = {}   # filepath → md5 hash
        self._running        = True

        # Lazy-import chromadb (installed by ingest.py if missing)
        try:
            import chromadb
        except ImportError:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                   "chromadb", "-q", "--break-system-packages"])
            import chromadb

        client = chromadb.PersistentClient(path=str(self.chroma_dir))
        self.collection = client.get_or_create_collection(self.collection_name)

        # Graceful shutdown on SIGINT / SIGTERM
        signal.signal(signal.SIGINT,  self._stop)
        signal.signal(signal.SIGTERM, self._stop)

    def _stop(self, *_):
        print("\n[watcher] Shutting down…")
        self._running = False

    def _file_hash(self, path: Path) -> str:
        return hashlib.md5(path.read_bytes()).hexdigest()

    def _scan(self):
        """Check for new or modified files and ingest them."""
        try:
            files = {
                f for f in self.docs_dir.iterdir()
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
            }
        except FileNotFoundError:
            print(f"[watcher] Documents folder not found: {self.docs_dir}")
            return

        for f in sorted(files):
            try:
                current_hash = self._file_hash(f)
            except OSError:
                continue  # file may have disappeared mid-scan

            prev_hash = self.seen_hashes.get(str(f))
            if current_hash != prev_hash:
                # New file or file has changed
                action = "Modified" if prev_hash else "New file"
                print(f"[watcher] {action} detected: {f.name}")
                ingest_file(f, self.collection, current_hash)
                self.seen_hashes[str(f)] = current_hash

    def run(self):
        print(f"[watcher] Started — watching {self.docs_dir}")
        print(f"[watcher] Collection: {self.collection_name} | "
              f"Poll interval: {self.interval}s")
        print(f"[watcher] Press Ctrl+C to stop.\n")

        # Initial pass on startup
        self._scan()

        while self._running:
            time.sleep(self.interval)
            self._scan()

        print("[watcher] Stopped.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Watch documents/ folder and auto-ingest new files into ChromaDB"
    )
    parser.add_argument("--docs",       required=True,
                        help="Path to documents/ folder")
    parser.add_argument("--collection", required=True,
                        help="ChromaDB collection name (usually business slug)")
    parser.add_argument("--chroma-dir", required=True,
                        help="ChromaDB persistence directory")
    parser.add_argument("--interval",   type=int, default=DEFAULT_INTERVAL,
                        help=f"Poll interval in seconds (default: {DEFAULT_INTERVAL})")
    args = parser.parse_args()

    docs_dir   = Path(args.docs)
    chroma_dir = Path(args.chroma_dir)

    if not docs_dir.exists():
        print(f"[watcher] Documents folder not found: {docs_dir}")
        sys.exit(1)

    chroma_dir.mkdir(parents=True, exist_ok=True)

    watcher = FolderWatcher(
        docs_dir        = docs_dir,
        collection_name = args.collection,
        chroma_dir      = chroma_dir,
        interval        = args.interval,
    )
    watcher.run()


if __name__ == "__main__":
    main()
