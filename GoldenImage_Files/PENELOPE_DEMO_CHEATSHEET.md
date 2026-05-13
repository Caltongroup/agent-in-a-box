# 🟢 PENELOPE DEMO CHEAT SHEET

**Tuesday April 7 | 2:00 PM MT | PEO Demo**

---

## 📡 CONNECTION

| Item | Details |
|------|---------|
| **Web UI (phone/laptop)** | http://192.168.68.58:5000 |
| **SSH to Pi** | ssh pi@192.168.68.58 |
| **PocketBase Admin** | http://192.168.68.58:8090/_ |
| **PB Login** | admin2@penelope.local / Penelope12345 |

---

## 🎯 DEMO FLOW — DO THIS FIRST

### Step 1
Open http://192.168.68.58:5000 on your phone

### Step 2
Ask a warm-up question yourself before they do

### Step 3 — Timing
- Loading message: **~3 sec**
- Answer: **~35-44 sec**

**What to say:**
> "It's reviewing your HR documents — takes about 35 seconds"

---

## 💬 SAMPLE QUESTIONS THAT WORK

| Question | Category |
|----------|----------|
| How much paid sick time do employees accrue per pay period? | Sick time |
| How many vacation days do new employees get in their first year? | Vacation |
| What about sick time? | Follow-up (tests conversation memory — ~35 sec) |
| What are the FMLA eligibility requirements? | FMLA |
| How many floating holidays do employees receive? | Floating holiday |

---

## 🔍 CHECK IF EVERYTHING IS RUNNING

| Command | Purpose |
|---------|---------|
| `python3 ~/GoldenImage_Files/penelope_demo_test.py` | Run validator |
| `sudo systemctl status hermes-webui` | Check web UI service |
| `sudo systemctl status ollama pocketbase hermes-webui` | Check all services |
| `sudo journalctl -u hermes-webui -f` | Watch live logs |

---

## 🔄 RESTART COMMANDS (if something is wrong)

| Action | Command |
|--------|---------|
| Restart web UI | `sudo systemctl restart hermes-webui` |
| Restart Ollama | `sudo systemctl restart ollama` |
| Restart PocketBase | `sudo systemctl restart pocketbase` |
| Restart EVERYTHING | `sudo reboot` (wait 90 seconds) |

---

## ✅ CONFIRM IT CAME BACK UP

Watch for these lines in the logs:

```
[WARMUP] qwen2.5:1.5b ready.
[WARMUP] nomic-embed-text ready.
[RAG]  ChromaDB loaded from ...  (collection: iliad_media_group)
```

---

## ⚠️ IF YOU GET A WRONG OR WEIRD ANSWER

| Issue | Cause | Fix |
|-------|-------|-----|
| Wrong or weird answer (1st time) | First question after restart — ChromaDB thread opening (normal) | Ask a second question — should be correct and ~9 sec faster |
| Model hedging | Model avoiding commitment | Ask again more specifically |
| Completely wrong answers | Data mismatch or service issue | Restart: `sudo systemctl restart hermes-webui` |

---

## ☢️ NUCLEAR OPTION — Full Reboot

**From Pi terminal:**
```bash
sudo reboot
```

**Wait:** 90 seconds, then hit http://192.168.68.58:5000

**If Pi offline:**
1. Unplug power
2. Wait 10 seconds
3. Plug back in
4. Wait 90 seconds

---

## 📝 DEMO SCRIPT

1. **Open web UI** on phone (http://192.168.68.58:5000)
2. **Ask warm-up question** yourself (e.g., "How much sick time?")
3. **Tell them:** "It's reviewing your HR documents — takes about 35 seconds"
4. **Wait for answer** (~35-44 sec)
5. **Ask follow-up** (e.g., "What about vacation?") — should be ~9 seconds
6. **Close:** "That's Penelope. Private AI that knows your HR policy. No cloud. No per-token costs."

---

**Built by Archer | April 7, 2026**
