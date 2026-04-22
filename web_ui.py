#!/usr/bin/env python3
"""
hermes/web_ui.py — Penelope Web Interface
Streaming Flask chat UI for local network access.

Usage:
    source ~/penelope_venv/bin/activate
    python3 hermes/web_ui.py --soul /home/pi/my_agent/SOUL.md \
                              --chroma-db /home/pi/my_agent/chroma_db \
                              --agent-name "Penelope"

Access from any device on the network:
    http://<pi-ip>:5000
"""

import argparse
import json
import os
import queue
import requests
import sys
import threading
from pathlib import Path
from flask import Flask, Response, request, stream_with_context

# Optional ChromaDB RAG — graceful fallback if not installed
try:
    import chromadb
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

# ── Configuration ─────────────────────────────────────────────────────────────
OLLAMA_URL   = "http://localhost:11434"           # used for embeddings only
LLAMA_URL   = "http://127.0.0.1:8080"            # llama-server (direct, no Ollama overhead)
MODEL        = "qwen2.5:1.5b"
PB_URL       = "http://127.0.0.1:8090"
MAX_HISTORY  = 10       # rolling turns kept in memory
NUM_CTX      = 2048     # set at llama-server startup via --ctx-size
NUM_PREDICT  = 150       # cap response tokens

# ── App state (module-level, single-process) ───────────────────────────────────
app              = Flask(__name__)
_history         = []          # list of {role, content} dicts
_soul_text       = ""
_chroma_col      = None        # used only for /health check (main thread only)
_chroma_db_path  = ""          # path passed to worker thread to create its own client
_chroma_col_name = ""          # collection name passed to worker thread
_agent_name      = "Penelope"
_thread_local    = threading.local()  # per-thread ChromaDB client cache

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_soul(soul_path: str) -> str:
    """Load SOUL.md; fall back to a sensible default."""
    p = Path(soul_path) if soul_path else None
    if p and p.exists():
        return p.read_text()
    return (
        "You are Penelope, a helpful and professional AI assistant. "
        "Keep replies concise and to the point unless asked for detail."
    )


def hyde_rewrite(query: str) -> str:
    """Generate a hypothetical policy-doc answer and embed that instead of the raw question."""
    try:
        r = requests.post(f"{LLAMA_URL}/v1/chat/completions", json={
            "model":      MODEL,
            "messages": [
                {"role": "system", "content": "You are a company policy document. Answer the question in one factual sentence using specific numbers and formal policy language."},
                {"role": "user", "content": query}
            ],
            "stream": False, "max_tokens": 60, "temperature": 0,
        }, timeout=60)
        answer = r.json()["choices"][0]["message"]["content"].strip()
        if answer:
            print(f"[HyDE] Q: {query[:60]}  →  {answer[:60]}")
            return answer
    except Exception as e:
        print(f"[HyDE] fallback: {e}")
    return query



def classify_question(query: str) -> str:
    q = query.lower()
    if any(x in q for x in ['insurance','dental','vision','deductible','premium','copay','benefit','medical','coverage','health plan']):
        return 'benefits'
    if any(x in q for x in ['smoking','smoke','vape','conduct','discipline','harassment','drug test','alcohol','weapon','violence','policy','compliance']):
        return 'policy'
    if any(x in q for x in ['vacation','sick','pto','leave','holiday','time off','bereavement','jury','absence','handbook','pay','salary','overtime']):
        return 'handbook'
    if any(x in q for x in ['onboard','new hire','first day','orientation','start','recruiting','offer','esop']):
        return 'onboarding'
    if any(x in q for x in ['termination','resign','offboard','exit','separation','fired','quit','last day']):
        return 'offboarding'
    return 'general'

def rag_context(query: str) -> str:
    """Return relevant document chunks from ChromaDB, or empty string.

    Uses threading.local() to cache one PersistentClient per thread —
    thread-safe and avoids re-opening SQLite on every request.
    Embeddings stay on Ollama (nomic-embed-text is already 0.06s warm).
    """
    if not _chroma_db_path or not _chroma_col_name:
        return ""
    try:
        if not hasattr(_thread_local, "col"):
            client = chromadb.PersistentClient(path=_chroma_db_path)
            _thread_local.col = client.get_collection(_chroma_col_name)
        emb = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": query},
            timeout=10,
        ).json()["embedding"]
        _where = None
        source_filter = False
        ql = query.lower()
        if 'dental' in ql:
            _where = {'source': 'dental_summary.md'}
            source_filter = True
        elif 'vision' in ql:
            _where = {'source': 'vision_summary.txt'}
            source_filter = True
        results = _thread_local.col.query(
            query_embeddings=[emb], n_results=3,
            **(({'where': _where}) if _where else {})
        )
        threshold = 0.65 if source_filter else 0.45
        pairs = zip(results.get('documents',[[]])[0], results.get('distances',[[]])[0])
        docs = [d for d,dist in pairs if dist < threshold]
        if docs:
            return "\n\nRelevant context:\n" + "\n---\n".join(docs)
    except Exception as e:
        print(f"[RAG] Error in worker thread: {e}", flush=True)
    return ""


def pb_log(user_msg: str, assistant_msg: str) -> None:
    """Fire-and-forget log to PocketBase sessions collection."""
    try:
        requests.post(
            f"{PB_URL}/api/collections/sessions/records",
            json={
                "summary": f"User: {user_msg[:300]}\nAssistant: {assistant_msg[:300]}",
                "type":    "web",
                "chat_id": "web",
            },
            timeout=3,
        )
    except Exception:
        pass


def warm_up_model() -> None:
    """Pre-load both models into RAM so first query has no cold-start penalty."""
    # Warm up chat model via llama-server (direct — no Ollama overhead)
    print(f"[WARMUP] Loading {MODEL} into memory via llama-server...")
    try:
        requests.post(
            f"{LLAMA_URL}/v1/chat/completions",
            json={
                "model":      MODEL,
                "messages":   [{"role": "user", "content": "hi"}],
                "stream":     False,
                "max_tokens": 1,
            },
            timeout=120,
        )
        print(f"[WARMUP] {MODEL} ready.")
    except Exception as e:
        print(f"[WARMUP] Warning ({MODEL}): {e}")

    # Warm up embedding model via Ollama — stays here, already 0.06s warm
    print("[WARMUP] Loading nomic-embed-text into memory...")
    try:
        requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": "warmup"},
            timeout=60,
        )
        print("[WARMUP] nomic-embed-text ready.")
    except Exception as e:
        print(f"[WARMUP] Warning (nomic-embed-text): {e}")


def stream_chat(user_message: str):
    """Generator: streams SSE tokens from llama-server with keepalive heartbeat.

    Sends a silent SSE comment every 5 s while the model is loading so mobile
    browsers don't close the connection during the cold-start period.
    """
    global _history

    _history.append({"role": "user", "content": user_message})
    if len(_history) > MAX_HISTORY * 2:
        _history = _history[-(MAX_HISTORY * 2):]

    # Queue used to pass SSE events from the worker thread to this generator
    q: queue.Queue = queue.Queue()
    full_reply_box = [""]   # mutable container so the thread can write to it

    def ollama_worker():
        # RAG runs INSIDE the thread — keepalives start immediately while this runs
        ctx = rag_context(user_message)
        if ctx:
            user_content = (
                "If the context below does not contain enough information to answer the question, respond only with: 'I don\'t have that information — please check with HR or your manager.' Otherwise, use ONLY the following policy excerpts to answer. "
                "State the exact number and unit from the document in your first sentence. "
                "Never say 'may vary', 'typically', 'consult HR', or hedge in any way — the document has the answer, state it directly. "
                "Read the question carefully. If the question asks about options or choices, list ALL of them from the context. If it asks about a specific situation, answer only that. Be concise — use bullet points for lists, 1-2 sentences for single facts.\n\n"
                f"---\n{ctx}\n---\n\n"
                f"Question: {user_message}"
            )
        else:
            user_content = user_message

        # llama-server uses OpenAI-compatible format
        # num_ctx is set at server startup (--ctx-size), not per-request
        payload = {
            "model":      MODEL,
            "messages":    [{"role": "system", "content": _soul_text}] + _history[:-1]
                           + [{"role": "user", "content": user_content}],
            "stream":      True,
            "max_tokens":  NUM_PREDICT,
            "temperature": 0.1,
        }

        full = ""
        try:
            with requests.post(
                f"{LLAMA_URL}/v1/chat/completions",
                json=payload,
                stream=True,
                timeout=180,
            ) as resp:
                print(f"[WORKER] llama status={resp.status_code}", flush=True)
                if resp.status_code != 200: print(f"[WORKER] error body={resp.text[:500]}", flush=True)
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                    if not line_str.startswith("data: "):
                        continue
                    data_str = line_str[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if choices:
                            token = choices[0].get("delta", {}).get("content", "") or ""
                            if token:
                                full += token
                                q.put(f"data: {json.dumps({'token': token})}\n\n")
                            if choices[0].get("finish_reason") == "stop":
                                break
                    except json.JSONDecodeError:
                        continue
        except requests.exceptions.ConnectionError:
            q.put(f"data: {json.dumps({'error': 'Cannot reach llama-server. Is it running?'})}\n\n")
        except Exception as e:
            import traceback
            print(f"[WORKER ERROR] {traceback.format_exc()}", flush=True)
            q.put(f"data: {json.dumps({'error': str(e)})}\n\n")
        finally:
            full_reply_box[0] = full
            q.put(None)   # sentinel — signals generator to stop

    t = threading.Thread(target=ollama_worker, daemon=True)
    t.start()

    # Yield tokens as they arrive; send keepalive comments while waiting
    while True:
        try:
            item = q.get(timeout=2)
        except queue.Empty:
            # Send a real data event — iOS Safari ignores SSE comments
            yield f"data: {json.dumps({'typing': True})}\n\n"
            continue

        if item is None:
            break
        yield item

    full_reply = full_reply_box[0]
    if full_reply:
        _history.append({"role": "assistant", "content": full_reply})
        pb_log(user_message, full_reply)

    yield f"data: {json.dumps({'done': True})}\n\n"


# ── HTML (single-file, no external dependencies) ─────────────────────────────

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{AGENT_NAME}}</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#f0f2f5;height:100vh;display:flex;flex-direction:column}
  header{background:#1a1a2e;color:#fff;padding:14px 24px;
         display:flex;align-items:center;gap:10px;flex-shrink:0}
  header h1{font-size:1.1rem;font-weight:600;letter-spacing:.3px}
  .dot{width:9px;height:9px;background:#4ade80;border-radius:50%;
       animation:pulse 2s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
  #chat{flex:1;overflow-y:auto;padding:20px 24px;
        display:flex;flex-direction:column;gap:14px}
  .bubble{max-width:72%;padding:11px 15px;border-radius:18px;
          line-height:1.55;font-size:.93rem;white-space:pre-wrap;word-wrap:break-word}
  .user{align-self:flex-end;background:#1a1a2e;color:#fff;
        border-bottom-right-radius:4px}
  .bot{align-self:flex-start;background:#fff;color:#1a1a2e;
       border-bottom-left-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
  .typing::after{content:'▌';animation:blink .65s infinite}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
  #bar{padding:14px 20px;background:#fff;border-top:1px solid #e2e2e2;
       display:flex;gap:10px;flex-shrink:0}
  #inp{flex:1;padding:11px 16px;border:1px solid #ddd;border-radius:22px;
       font-size:.93rem;outline:none;font-family:inherit;resize:none;
       max-height:120px;overflow-y:auto}
  #inp:focus{border-color:#1a1a2e}
  #btn{background:#1a1a2e;color:#fff;border:none;border-radius:22px;
       padding:11px 22px;cursor:pointer;font-size:.93rem;font-weight:500;
       white-space:nowrap}
  #btn:disabled{opacity:.45;cursor:not-allowed}
  #btn:hover:not(:disabled){background:#16213e}
  @media(max-width:600px){.bubble{max-width:88%}#chat{padding:14px}
    #bar{padding:10px 12px}}
</style>
</head>
<body>
<header>
  <div class="dot"></div>
  <h1>{{AGENT_NAME}}</h1>
</header>
<div id="chat"></div>
<div id="bar">
  <textarea id="inp" rows="1" placeholder="Ask {{AGENT_NAME}} something…"></textarea>
  <button id="btn">Send</button>
</div>
<script>
const chat=document.getElementById('chat');
const inp=document.getElementById('inp');
const btn=document.getElementById('btn');

function addBubble(text,role){
  const d=document.createElement('div');
  d.className='bubble '+(role==='user'?'user':'bot');
  d.textContent=text;
  chat.appendChild(d);
  chat.scrollTop=chat.scrollHeight;
  return d;
}

// Auto-grow textarea
inp.addEventListener('input',()=>{
  inp.style.height='auto';
  inp.style.height=Math.min(inp.scrollHeight,120)+'px';
});

async function send(){
  const text=inp.value.trim();
  if(!text||btn.disabled)return;
  inp.value='';inp.style.height='auto';
  btn.disabled=true;

  addBubble(text,'user');
  const reply=addBubble('','bot');
  reply.classList.add('typing');

  try{
    const r=await fetch('/chat',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:text})
    });
    const reader=r.body.getReader();
    const dec=new TextDecoder();
    let buf='';
    while(true){
      const{done,value}=await reader.read();
      if(done)break;
      buf+=dec.decode(value,{stream:true});
      const lines=buf.split('\\n');
      buf=lines.pop();
      for(const line of lines){
        if(!line.startsWith('data: '))continue;
        const d=JSON.parse(line.slice(6));
        if(d.typing&&!reply.dataset.started){
          reply.textContent='Searching documents…';
          reply.style.fontStyle='italic';reply.style.opacity='0.7';}
        if(d.token){
          if(!reply.dataset.started){
            reply.textContent='';reply.style.fontStyle='';reply.style.opacity='';}
          reply.dataset.started='1';
          reply.classList.remove('typing');
          reply.textContent+=d.token;
          chat.scrollTop=chat.scrollHeight;}
        if(d.done||d.error){reply.classList.remove('typing');
                             if(d.error)reply.textContent='⚠ '+d.error;}
      }
    }
  }catch(e){
    reply.classList.remove('typing');
    reply.textContent='⚠ Connection error. Is Penelope running?';
  }
  btn.disabled=false;
  inp.focus();
}

btn.addEventListener('click',send);
inp.addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}
});
inp.focus();
</script>
</body>
</html>
"""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return _HTML.replace("{{AGENT_NAME}}", _agent_name)


@app.route("/chat", methods=["POST"])
def chat_endpoint():
    data    = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return Response(
            'data: {"error":"empty message"}\n\n',
            mimetype="text/event-stream",
        )
    return Response(
        stream_with_context(stream_chat(message)),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



@app.route("/ask", methods=["POST"])
def ask_endpoint():
    """Non-streaming endpoint for Telegram bot."""
    data    = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return {"error": "empty message"}, 400
    full = ""
    for chunk in stream_chat(message):
        if chunk.startswith("data: "):
            try:
                d = json.loads(chunk[6:])
                if "token" in d:
                    full += d["token"]
            except Exception:
                pass
    return {"response": full}

@app.route("/health")
def health():
    return {"status": "ok", "model": MODEL, "rag": _chroma_col is not None}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Penelope Web UI")
    parser.add_argument("--soul",       help="Path to SOUL.md")
    parser.add_argument("--chroma-db",   help="Path to chroma_db directory")
    parser.add_argument("--collection",  default=None, help="ChromaDB collection name")
    parser.add_argument("--agent-name",  default="Penelope", help="Display name")
    parser.add_argument("--port",       type=int, default=5000)
    parser.add_argument("--host",       default="0.0.0.0")
    args = parser.parse_args()

    # Populate module-level state
    _soul_text  = load_soul(args.soul)
    _agent_name = args.agent_name

    if HAS_CHROMA and args.chroma_db:
        db_path = Path(args.chroma_db)
        if db_path.exists():
            try:
                col_name        = args.collection or args.agent_name.lower().replace(" ", "_")
                client          = chromadb.PersistentClient(path=str(db_path))
                _chroma_col     = client.get_collection(col_name)
                # Store path + name so worker threads can create their own clients
                _chroma_db_path  = str(db_path)
                _chroma_col_name = col_name
                print(f"[RAG]  ChromaDB loaded from {db_path}  (collection: {col_name})")
            except Exception as e:
                print(f"[RAG]  ChromaDB unavailable: {e}")
        else:
            print(f"[RAG]  Path not found, skipping: {db_path}")
    else:
        print("[RAG]  Disabled (no --chroma-db or chromadb not installed)")

    # Resolve network IP for display
    try:
        import socket
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "<pi-ip>"

    warm_up_model()

    print(f"\n{'─'*50}")
    print(f"  {_agent_name} Web UI is running")
    print(f"  Local:   http://localhost:{args.port}")
    print(f"  Network: http://{ip}:{args.port}")
    print(f"  Model:   {MODEL}  |  ctx:{NUM_CTX}  |  max_tokens:{NUM_PREDICT}")
    print(f"{'─'*50}\n")

    app.run(host=args.host, port=args.port, debug=False, threaded=True)
