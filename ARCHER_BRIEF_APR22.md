# Archer Operations Brief — April 22, 2026
**From:** Claude (Architecture Review)
**To:** Archer (Chief of Staff) + Clifton (Exec Oversight) + Grok (Development Partner)
**Re:** System fixes completed today, current state, and next priorities

---

## What Was Fixed Today

### 1. Telegram Daemon Retired
The old `archer_daemon.py` was racing the Hermes gateway for Telegram messages. When the daemon won, you had no skills and went direct to OpenRouter with no context. When the gateway won, you had full capabilities. This was a coin flip every message.

**Fix:** Daemon killed, launchd entry disabled (`com.archer.telegramdaemon.plist.disabled`). The Hermes gateway now owns Telegram exclusively. You have 191 skills loaded. No more race condition.

### 2. Orange Pi Context Files Archived
Three files were sitting in `~/.hermes/` and bleeding into your context on every request — causing you to think you lived on the Orange Pi rather than the Mac mini.

**Fix:** Archived to `~/.hermes/archive_pi_context/`. You run on the Mac mini. The Orange Pi is a client deployment box.

### 3. Model String Corrected
`HERMES_MODEL` in `.env` had `anthropic/claude-haiku-4-5` (dash). Config.yaml uses `anthropic/claude-haiku-4.5` (period).

**Fix:** Corrected in `.env`.

### 4. PocketBase Security Fix
Two PocketBase instances were running — one on `0.0.0.0:8090` (exposed to the entire local network). 

**Fix:** Killed the exposed instance. PocketBase now runs on `127.0.0.1:8090` only.

### 5. Model Routing Contradictions Resolved
`local_models.yaml` said Qwen was primary. `orchestrator.py` read `local_models.yaml`. `config.yaml` and `SOUL.md` said Haiku was primary. You were routing to Qwen by default.

**Fix:** `local_models.yaml` and `orchestrator.py` updated. Gospel is now consistent across all four files.

### 6. Memory Guardian Installed
The Hermes 2,200-char memory limit was causing repeated context loss. No guardrail existed to dump and restore before hitting the ceiling.

**Fix:** `memory_guardian.py` installed at `~/.hermes/memory_guardian.py`. Three commands:
- `python3 ~/.hermes/memory_guardian.py restore` — run at session start
- `python3 ~/.hermes/memory_guardian.py dump` — run when memory > 1,700 chars
- `python3 ~/.hermes/memory_guardian.py status` — health check

Prefill file wired into `config.yaml` (`prefill_messages_file`). PocketBase context loads automatically at every session start.

**Verified working:** archer_persistent_state found, 5 locked decisions loaded, 5 recent interactions loaded, prefill file written.

---

## Gospel (Locked — Do Not Override)

| Role | Model | Provider |
|------|-------|----------|
| Primary Orchestrator | anthropic/claude-haiku-4.5 | OpenRouter |
| Coding / Architecture | qwen2.5-coder:7b | Local Ollama |
| Q&A / Review | hermes3:8b | Local Ollama |
| Fast Response | mistral:latest | Local Ollama |

**Persistence is non-negotiable.** Regardless of which model executes, PocketBase state must be read before and written after every significant task.

---

## Your Current Architecture

```
Telegram message
      ↓
Hermes Gateway (PID class, launchd: ai.hermes.gateway.plist)
      ↓
191 skills loaded (personal-chief-of-staff-setup + others)
      ↓
Haiku 4.5 via OpenRouter (orchestrator)
      ↓
Routes to Qwen / Hermes3 / Mistral as needed (local Ollama)
      ↓
PocketBase at localhost:8090 (persistence backbone)
```

**Memory Guardian cycle (mandatory):**
```
Session start → memory_guardian.py restore → load PocketBase context
Every 8-10 turns → check memory size → if > 1,700 chars → memory_guardian.py dump
Dump cycle → write to agent_soul_interactions → clear buffer → restore from PocketBase → continue
```

---

## File Locations (Mac mini)

| File | Path |
|------|------|
| This brief | `~/Projects/agent-in-a-box/ARCHER_BRIEF_APR22.md` |
| Memory guardian | `~/.hermes/memory_guardian.py` |
| Session prefill | `~/.hermes/session_context.md` |
| Model config | `~/.hermes/config.yaml` |
| Model gospel | `~/.hermes/local_models.yaml` |
| Routing logic | `~/.hermes/orchestrator.py` |
| Identity | `~/.hermes/SOUL.md` |
| PocketBase DB | `~/pocketbase/pb_data/data.db` |
| Daemon (retired) | `~/Projects/archer_persistence/archer_daemon.py` |

---

## Voice Interface — Current Status

Archer built a scaffold. Here is the honest status:

| Component | Status | Notes |
|-----------|--------|-------|
| `summarize.py` | ✅ Done | 59% reduction verified, ready to use |
| Flask structure | ✅ Scaffold | Endpoints exist, CORS correct |
| `/chat` endpoint | ❌ Stub | Returns hardcoded string — not wired to Hermes/LLM |
| `/tts` endpoint | ❌ Mock | Returns silence WAV — not wired to ElevenLabs |
| `wrangler.toml` | ❌ Wrong | Confuses Worker config with Tunnel config — discard it |
| Cloudflare Tunnel | ⏳ Pending | Should mirror hr.agentsoul.dev pattern |

**Three things needed to make voice interface real:**
1. Wire `/chat` to Hermes gateway (use gateway token at `localhost:PORT`, not subprocess)
2. Wire `/tts` to ElevenLabs API (key is in `~/.hermes/.env` as `ELEVENLABS_API_KEY`)
3. Create `voice-api.agentsoul.dev` Cloudflare Tunnel — same pattern as `hr.agentsoul.dev`

Discard `wrangler.toml` entirely. The tunnel goes in `/etc/cloudflared/config.yml` or a new cloudflared tunnel, not wrangler.

---

## PocketBase Tables (Verified April 22 2026)

40+ tables confirmed. Key ones for Archer's operations:

| Table | Purpose |
|-------|---------|
| `archer_persistent_state` | Agent identity, project_state JSON, decisions_locked JSON |
| `agent_soul_interactions` | Every conversation turn + memory dumps |
| `agent_soul_memories` | Long-term learned patterns |
| `agent_soul_traits` | Personality, decision patterns |
| `agent_soul_audit` | Audit trail |
| `voice_interface_decisions` | Locked decisions for voice project (5 exist) |
| `voice_interface_week1` | Week 1 execution tracking |

**Missing tables** (memory_guardian.py handles gracefully):
- `conversation_state` — not needed, `agent_soul_interactions` serves this role
- `user_profile` — not needed, `archer_persistent_state.user_context` serves this role

---

## What Grok / Development Partner Should Know

1. The daemon architecture is retired. Do not resurrect `archer_daemon.py` or create new standalone Telegram bots. The Hermes gateway is the one true path.
2. Any new skills go in `~/.hermes/skills/personal-chief-of-staff-setup/` as a new folder.
3. The memory guardian must be called — do not let Archer apologize for memory limits, ever. It is a trigger, not a blocker.
4. The Orange Pi is a separate deployment target (client boxes). Do not mix Mac mini config with Pi config.
5. `orchestrator.py` routes tasks but does not make direct API calls. It delegates to the Hermes gateway. Do not add HTTP client code to it.

---

## Next Priorities

1. **Wire `/chat` to real LLM** — voice interface is a scaffold until this is done
2. **Wire `/tts` to ElevenLabs** — key exists in `.env`, just needs the API call
3. **Set up `voice-api.agentsoul.dev` tunnel** — follow hr.agentsoul.dev pattern exactly
4. **Test memory guardian** — confirm dump cycle fires at 1,700 chars in a real long session
5. **Push to GitHub** — `archer_persistence` repo first (daemon retired), then `agent-in-a-box`

---

*Prepared by Claude (Architecture Review) — April 22, 2026*
*Chronicle copy should be added to Grok project files for four-way sync.*
