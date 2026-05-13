#!/usr/bin/env python3
# =============================================================================
# hermes/main.py — Penelope: Agent in a Box  |  Agent Core
# Decision ID: d3a11098-1cf6-444f-8293-7462a6e9e3cc  |  April 5, 2026
#
# Generic agent core. Works for any vertical. No vertical-specific code.
# Uses Ollama REST API directly (ARM-safe, no ollama Python package needed).
# RAG: ChromaDB + nomic-embed-text via Ollama.
# Persistence: PocketBase sessions collection.
# Personality: loaded from SOUL.md at startup.
# =============================================================================

import sys, argparse, json
from pathlib import Path
from datetime import datetime

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "-q", "--break-system-packages"])
    import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OLLAMA_URL    = "http://localhost:11434"
RAG_RESULTS   = 4       # number of ChromaDB chunks to inject per query
MAX_HISTORY   = 10      # conversation turns to keep in memory

# ---------------------------------------------------------------------------
# Ollama REST helpers (no ollama package required)
# ---------------------------------------------------------------------------
def ollama_embed(text: str, model: str) -> list[float]:
    r = requests.post(f"{OLLAMA_URL}/api/embeddings",
                      json={"model": model, "prompt": text}, timeout=60)
    r.raise_for_status()
    return r.json()["embedding"]


def ollama_chat(messages: list, model: str) -> str:
    r = requests.post(f"{OLLAMA_URL}/api/chat",
                      json={
                          "model":    model,
                          "messages": messages,
                          "stream":   False,
                          "options": {
                              "num_ctx":     4096,  # keep small — critical for speed on Pi
                              "num_predict": 300,   # hard cap on response tokens
                              "temperature": 0.7,
                          },
                      },
                      timeout=120)
    r.raise_for_status()
    return r.json()["message"]["content"]

# ---------------------------------------------------------------------------
# RAG — query ChromaDB for relevant context
# ---------------------------------------------------------------------------
def rag_query(question: str, collection_name: str,
              chroma_dir: Path, embed_model: str) -> str:
    """Return top-k relevant chunks as a formatted context string."""
    try:
        import chromadb
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "chromadb", "-q", "--break-system-packages"])
        import chromadb

    try:
        client     = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection(collection_name)

        if collection.count() == 0:
            return ""   # No documents indexed yet — answer from model only

        embedding = ollama_embed(question, embed_model)
        results   = collection.query(
            query_embeddings=[embedding],
            n_results=min(RAG_RESULTS, collection.count()),
            include=["documents", "metadatas"],
        )

        chunks = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            source = meta.get("source", "unknown")
            chunks.append(f"[Source: {source}]\n{doc}")

        return "\n\n---\n\n".join(chunks) if chunks else ""

    except Exception as e:
        print(f"  ⚠  RAG query error: {e}", file=sys.stderr)
        return ""

# ---------------------------------------------------------------------------
# PocketBase — log session (matches our sessions schema: summary field)
# ---------------------------------------------------------------------------
def pb_log(pb_url: str, question: str, answer: str, model: str):
    try:
        summary = f"Q: {question[:120]}\nA: {answer[:240]}"
        requests.post(
            f"{pb_url}/api/collections/sessions/records",
            json={"summary": summary},
            timeout=3,
        )
    except Exception:
        pass   # Logging failure never breaks the agent

# ---------------------------------------------------------------------------
# Conversation loop
# ---------------------------------------------------------------------------
def run_agent(args):
    # Load SOUL.md
    soul_path = Path(args.soul)
    if soul_path.exists():
        soul = soul_path.read_text().strip()
        print(f"  →  SOUL loaded: {soul_path}")
    else:
        soul = "You are a helpful, professional assistant."
        print(f"  ⚠  {soul_path} not found — using default personality")

    chroma_dir = Path(args.chroma_dir)
    model      = args.model        # phi3.5
    embed      = args.embed_model  # nomic-embed-text
    collection = args.collection

    # Check ChromaDB has indexed documents
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(chroma_dir))
        try:
            col   = client.get_collection(collection)
            count = col.count()
            print(f"  →  ChromaDB: {count} chunks indexed in '{collection}'")
            if count == 0:
                print("  ⚠  No documents indexed yet. "
                      "Drop files in documents/ — watcher will pick them up.")
        except Exception:
            print(f"  ⚠  Collection '{collection}' not found — "
                  "agent will run without RAG until documents are indexed.")
    except Exception:
        print("  ⚠  ChromaDB unavailable — running without RAG")

    print(f"\n  Agent ready. Model: {model}  |  Type 'exit' to quit.\n")
    print("="*60)

    history = []   # rolling conversation history

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("  Goodbye.")
            break

        # 1. Retrieve RAG context
        context = rag_query(user_input, collection, chroma_dir, embed)

        # 2. Build user message — put RAG context directly in user turn
        #    Small models follow context more reliably here than in system prompt
        if context:
            user_content = (
                "Use ONLY the following policy excerpts to answer. "
                "State the specific number, days, or figure directly in your first sentence. "
                "Be brief — 2-3 sentences maximum.\n\n"
                f"---\n{context}\n---\n\n"
                f"Question: {user_input}"
            )
        else:
            user_content = user_input

        # 3. Build messages with rolling history
        messages = [{"role": "system", "content": soul}]
        messages += history[-MAX_HISTORY:]
        messages.append({"role": "user", "content": user_content})

        # 4. Call Ollama
        try:
            answer = ollama_chat(messages, model)
        except Exception as e:
            print(f"  ✗  Model error: {e}")
            continue

        print(f"\nAgent: {answer}")

        # 5. Update history
        history.append({"role": "user",      "content": user_input})
        history.append({"role": "assistant", "content": answer})

        # 6. Log to PocketBase
        pb_log(args.pb_url, user_input, answer, model)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Penelope Hermes Agent — generic AI core"
    )
    parser.add_argument("--soul",         default="SOUL.md",
                        help="Path to SOUL.md personality file")
    parser.add_argument("--docs",         default="documents",
                        help="Path to documents folder (informational)")
    parser.add_argument("--chroma-dir",   default="chroma_db",
                        help="ChromaDB persistence directory")
    parser.add_argument("--collection",   default="main",
                        help="ChromaDB collection name")
    parser.add_argument("--pb-url",       default="http://localhost:8090",
                        help="PocketBase base URL")
    parser.add_argument("--pb-contacts",  default="contacts",
                        help="PocketBase contacts collection name")
    parser.add_argument("--model",        default="qwen2.5:1.5b",
                        help="Ollama model tag (default: phi3.5)")
    parser.add_argument("--embed-model",  default="nomic-embed-text",
                        help="Ollama embedding model (default: nomic-embed-text)")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  Penelope: Agent in a Box  |  Hermes Agent Core")
    print("="*60)

    run_agent(args)


if __name__ == "__main__":
    main()
