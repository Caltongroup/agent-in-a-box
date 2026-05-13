#!/usr/bin/env python3
# =============================================================================
# hermes/gateway.py — Penelope: Agent in a Box  |  Telegram Gateway
# Decision ID: d3a11098-1cf6-444f-8293-7462a6e9e3cc  |  April 5, 2026
#
# Patches applied (April 5 review):
#   [1] Telegram whitelist — only contacts with a telegram_chat_id can message
#   [2] Model warm-up — loads Phi-3.5-mini into RAM before first message,
#       sends "Penelope is online" to all authorised users after reboot
#   [3] History persisted to PocketBase — survives restarts
# =============================================================================

import sys, argparse, time, json
from pathlib import Path

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "-q", "--break-system-packages"])
    import requests

OLLAMA_URL       = "http://localhost:11434"
RAG_RESULTS      = 4
MAX_HISTORY      = 10
WHITELIST_REFRESH = 50   # reload whitelist every N messages processed

# ---------------------------------------------------------------------------
# Ollama REST
# ---------------------------------------------------------------------------
def ollama_embed(text, model):
    r = requests.post(f"{OLLAMA_URL}/api/embeddings",
                      json={"model": model, "prompt": text}, timeout=60)
    r.raise_for_status()
    return r.json()["embedding"]

def ollama_chat(messages, model):
    r = requests.post(f"{OLLAMA_URL}/api/chat",
                      json={"model": model, "messages": messages, "stream": False},
                      timeout=120)
    r.raise_for_status()
    return r.json()["message"]["content"]

# ---------------------------------------------------------------------------
# [2] Model warm-up — load model into RAM before first real message
# ---------------------------------------------------------------------------
def warm_up_model(model: str, soul: str) -> bool:
    print("  →  Warming up model (loading into RAM)…", flush=True)
    try:
        ollama_chat([
            {"role": "system",  "content": soul},
            {"role": "user",    "content": "Hello"},
        ], model)
        print("  ✓  Model warm — ready for messages")
        return True
    except Exception as e:
        print(f"  ⚠  Warm-up failed: {e}", file=sys.stderr)
        return False

# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------
def rag_query(question, collection_name, chroma_dir, embed_model):
    try:
        import chromadb
        client     = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection(collection_name)
        if collection.count() == 0:
            return ""
        embedding = ollama_embed(question, embed_model)
        results   = collection.query(
            query_embeddings=[embedding],
            n_results=min(RAG_RESULTS, collection.count()),
            include=["documents", "metadatas"],
        )
        chunks = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            chunks.append(f"[Source: {meta.get('source','?')}]\n{doc}")
        return "\n\n---\n\n".join(chunks)
    except Exception as e:
        print(f"  ⚠  RAG error: {e}", file=sys.stderr)
        return ""

# ---------------------------------------------------------------------------
# PocketBase — whitelist, logging, history persistence
# ---------------------------------------------------------------------------
def pb_load_whitelist(pb_url: str, contacts_col: str) -> set:
    """Return set of allowed Telegram chat_ids from contacts collection."""
    try:
        r = requests.get(
            f"{pb_url}/api/collections/{contacts_col}/records",
            params={"perPage": 200}, timeout=5
        )
        if r.status_code != 200:
            return set()
        ids = set()
        for rec in r.json().get("items", []):
            cid = rec.get("telegram_chat_id", "").strip()
            if cid:
                try:
                    ids.add(int(cid))
                except ValueError:
                    pass
        return ids
    except Exception:
        return set()

def pb_log(pb_url, chat_id, question, answer):
    try:
        summary = f"[Telegram {chat_id}] Q: {question[:120]}\nA: {answer[:240]}"
        requests.post(f"{pb_url}/api/collections/sessions/records",
                      json={"summary": summary, "chat_id": str(chat_id)},
                      timeout=3)
    except Exception:
        pass

# [3] History persistence — store per chat_id as JSON in PocketBase
def pb_load_history(pb_url, chat_id):
    try:
        r = requests.get(
            f"{pb_url}/api/collections/sessions/records",
            params={"filter": f'chat_id="{chat_id}" && type="history"',
                    "sort": "-created", "perPage": 1},
            timeout=5
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            if items:
                return json.loads(items[0].get("summary", "[]"))
    except Exception:
        pass
    return []

def pb_save_history(pb_url, chat_id, history):
    try:
        # Upsert: delete old history record, write new one
        r = requests.get(
            f"{pb_url}/api/collections/sessions/records",
            params={"filter": f'chat_id="{chat_id}" && type="history"',
                    "perPage": 1},
            timeout=5
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            for item in items:
                requests.delete(
                    f"{pb_url}/api/collections/sessions/records/{item['id']}",
                    timeout=3)
        requests.post(
            f"{pb_url}/api/collections/sessions/records",
            json={"summary": json.dumps(history[-MAX_HISTORY:]),
                  "chat_id": str(chat_id), "type": "history"},
            timeout=3
        )
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Telegram Bot API helpers
# ---------------------------------------------------------------------------
def tg(token, method, **kwargs):
    url = f"https://api.telegram.org/bot{token}/{method}"
    r   = requests.post(url, json=kwargs, timeout=10)
    return r.json() if r.ok else {}

def send_message(token, chat_id, text):
    for chunk in [text[i:i+4096] for i in range(0, len(text), 4096)]:
        tg(token, "sendMessage", chat_id=chat_id, text=chunk)

def get_updates(token, offset):
    result = tg(token, "getUpdates", offset=offset, timeout=30)
    return result.get("result", [])

# ---------------------------------------------------------------------------
# Gateway loop
# ---------------------------------------------------------------------------
def run_gateway(args):
    soul_path  = Path(args.soul)
    chroma_dir = Path(args.chroma_dir)
    soul       = soul_path.read_text().strip() if soul_path.exists() \
                 else "You are a helpful, professional assistant."

    print(f"  →  SOUL: {soul_path}" if soul_path.exists()
          else "  ⚠  SOUL.md not found — using default personality")
    print(f"  →  Mode: {args.mode} | Model: {args.model}")

    # Verify bot token
    me = tg(args.token, "getMe")
    if not me.get("ok"):
        print("  ✗  Telegram token invalid or network unavailable.", file=sys.stderr)
        sys.exit(1)
    bot_name = me["result"].get("username", "unknown")
    print(f"  ✓  Telegram bot connected: @{bot_name}")

    # [1] Load whitelist
    whitelist = pb_load_whitelist(args.pb_url, args.pb_contacts)
    if whitelist:
        print(f"  ✓  Whitelist loaded: {len(whitelist)} authorised user(s)")
    else:
        print("  ⚠  No Telegram chat IDs found in contacts — "
              "OPEN TO ALL USERS. Add telegram_chat_id to contacts to restrict.")

    # [2] Warm up model before accepting messages
    warm_up_model(args.model, soul)

    # [2] Notify all whitelisted users that Penelope is back online
    if whitelist:
        for cid in whitelist:
            send_message(args.token, cid,
                         f"✅ *Penelope is online and ready.*\n"
                         f"Ask me anything — I have your documents loaded.")

    print(f"\n  Gateway ready. Listening for messages to @{bot_name}.\n")
    print("="*60)

    offset     = 0
    msg_count  = 0

    while True:
        try:
            updates = get_updates(args.token, offset)
        except Exception as e:
            print(f"  ⚠  Poll error: {e} — retrying in 5s")
            time.sleep(5)
            continue

        for update in updates:
            offset    = update["update_id"] + 1
            msg       = update.get("message", {})
            text      = msg.get("text", "").strip()
            chat_id   = msg.get("chat", {}).get("id")
            user_name = msg.get("from", {}).get("first_name", "there")

            if not text or not chat_id:
                continue

            # [1] Enforce whitelist
            if whitelist and chat_id not in whitelist:
                send_message(args.token, chat_id,
                             "Sorry, you're not authorised to use this assistant. "
                             "Please contact your administrator.")
                print(f"  ✗  Blocked unauthorised user: {chat_id}")
                continue

            print(f"  ← [{chat_id}] {text[:80]}")
            msg_count += 1

            # Refresh whitelist periodically
            if msg_count % WHITELIST_REFRESH == 0:
                whitelist = pb_load_whitelist(args.pb_url, args.pb_contacts)

            # /start
            if text.startswith("/start"):
                send_message(args.token, chat_id,
                             f"👋 Hello {user_name}! I'm your Penelope assistant.\n"
                             f"Ask me anything — I have access to your documents.\n\n"
                             f"Commands: /reset (clear history)")
                continue

            # /reset
            if text.startswith("/reset"):
                pb_save_history(args.pb_url, chat_id, [])
                send_message(args.token, chat_id, "✅ Conversation history cleared.")
                continue

            # RAG context
            context = rag_query(text, args.collection, chroma_dir, args.embed_model)

            # System prompt
            system_content = soul
            if context:
                system_content += (
                    "\n\n## Relevant Documents\n"
                    "Use the following excerpts to answer. "
                    "Always cite the source document name.\n\n" + context
                )

            # [3] Load persisted history
            history  = pb_load_history(args.pb_url, chat_id)
            messages = [{"role": "system", "content": system_content}]
            messages += history[-MAX_HISTORY:]
            messages.append({"role": "user", "content": text})

            # Call Ollama
            try:
                answer = ollama_chat(messages, args.model)
            except Exception as e:
                send_message(args.token, chat_id,
                             f"⚠️ Model error — please try again.\n({e})")
                continue

            send_message(args.token, chat_id, answer)
            print(f"  → [{chat_id}] {answer[:80]}…")

            # [3] Persist updated history
            history.append({"role": "user",      "content": text})
            history.append({"role": "assistant", "content": answer})
            pb_save_history(args.pb_url, chat_id, history)

            pb_log(args.pb_url, chat_id, text, answer)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Penelope Hermes Gateway — Telegram bridge"
    )
    parser.add_argument("--mode",        default="telegram")
    parser.add_argument("--token",       required=True,
                        help="Telegram bot token (from @BotFather)")
    parser.add_argument("--pb-url",      default="http://localhost:8090")
    parser.add_argument("--pb-contacts", default="contacts",
                        help="PocketBase contacts collection name")
    parser.add_argument("--port",        type=int, default=8091)
    parser.add_argument("--soul",        default="SOUL.md")
    parser.add_argument("--chroma-dir",  default="chroma_db")
    parser.add_argument("--collection",  default="main")
    parser.add_argument("--model",       default="phi3.5")
    parser.add_argument("--embed-model", default="nomic-embed-text")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  Penelope: Agent in a Box  |  Hermes Gateway")
    print("="*60)

    run_gateway(args)

if __name__ == "__main__":
    main()
