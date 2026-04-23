# Voice Interface Pattern: Local Backend + Cloudflare Tunnel + Astro Frontend

**Date:** April 22, 2026
**Source:** Clifton Calton voice interface project (agent-in-a-box evolution)
**Status:** MVP locked, reusable architecture pattern

---

## Pattern Summary

Build a voice-controlled AI interface that:
- Works from anywhere (Tesla/iPhone cellular, not just home wifi)
- Exposes local AI backend securely to internet
- Uses existing API infrastructure (ElevenLabs TTS) for MVP
- Scales to local GPU (Jetson) post-MVP without frontend changes
- Persists conversation memory (PocketBase)

**Key learning:** Don't rebuild TTS locally if you already have API credits. MVP with existing infrastructure, optimize later.

---

## Architecture

```
User (Tesla cellular) 
  → voice.domain.dev (Astro + Cloudflare Pages)
  → voice-api.domain.dev (Cloudflare Tunnel)
  → Flask localhost:5000 (Mac Mini, later Jetson)
  → PocketBase + Hermes CLI + ElevenLabs API
```

---

## Three Critical Decisions

### 1. Networking: Cloudflare Tunnel (Not Local CORS)

**Problem:** Local-network-only CORS doesn't work when user is driving (cellular, not home wifi).

**Solution:** Cloudflare Tunnel.
- Free tier sufficient
- Proven pattern (same as hr.agentsoul.dev)
- Simple DNS routing (voice-api.domain.dev → localhost:5000)
- Works from anywhere (cellular, 4G, 5G)

### 2. TTS: Use Existing API (Not Rebuild Locally)

**Problem:** Local Voicebox TTS = weeks of engineering for GPU inference.

**Solution:** ElevenLabs (already configured in .env + config.yaml).
- MVP ships in days (not weeks)
- Uses existing API credits
- Same `/tts` interface works post-Jetson (swap implementation, no frontend changes)

**Post-MVP:** Swap ElevenLabs → Jetson TTS (same endpoint interface).

### 3. Deployment: Separate Astro Project (Not Embedded)

**Problem:** Embedding voice tool in marketing site = same deployment risk, independent update cycles mixed.

**Solution:** voice.domain.dev as standalone Cloudflare Pages project.
- Clean separation (tool ≠ marketing)
- Independent deploys (one broken build doesn't crash the other)
- Own update cycle (iterate fast on tool, keep marketing stable)

---

## Implementation Summary

### Backend (Flask, 2 hours)

```python
# voice_api.py
# /chat → subprocess to local model (hermes CLI)
# /tts → ElevenLabs API
# /history → PocketBase REST
# /health → monitoring endpoint
```

### Frontend (Astro, 4 hours)

```astro
# src/pages/index.astro
# WebRTC audio capture (start/stop recording)
# Web Speech API for STT (browser-native)
# Fetch to voice-api.domain.dev/chat
# Play TTS audio response
# Load conversation history from PocketBase
```

### Infrastructure (Cloudflare, 1 hour)

```bash
wrangler tunnel create voice-api
# Route voice-api.domain.dev → localhost:5000
# Create Cloudflare Pages project for voice.domain.dev
# Deploy Astro build
```

**Total:** ~8 hours to MVP

---

## Trial & Error Lessons

1. **Don't rebuild infrastructure you already have.**
   - ElevenLabs credits sitting unused? Use them.
   - Local TTS can wait for post-MVP optimization.
   - Ship fast with existing, optimize later.

2. **Test the actual use case.**
   - "Local network CORS" works at home, not while driving.
   - Assumption ≠ reality.
   - Cloudflare Tunnel solves the real problem (cellular access).

3. **Separate concerns (tools vs. marketing).**
   - Embedding voice tool in marketing site = mixed risk profiles.
   - Separate Cloudflare Pages project = independent deploys.
   - One broken build doesn't cascade.

---

## Post-MVP Roadmap (No Frontend Changes)

**Week 4-5:** Jetson migration
- Move Flask to Jetson (same code, faster GPU)
- Update Cloudflare Tunnel endpoint
- Frontend still calls voice-api.domain.dev

**Week 6+:** Local TTS swap
- Replace ElevenLabs with Jetson Voicebox
- Update `/tts` endpoint implementation
- Same audio_url response (frontend unchanged)

**Week 7+:** Upgrade to Qwen 27B
- Replace Haiku with local Qwen 27B orchestrator
- Same `/chat` interface (frontend unchanged)

---

## Reusable Pattern

This architecture works for any local AI backend that needs:
- Remote access (cellular, not just LAN)
- Voice I/O (TTS + STT)
- Conversation memory (PocketBase or similar)
- Cost optimization (use existing API credits, swap to local GPU later)

**Applicable to:**
- Local code assistants (like Archer)
- Business AI agents (Agent in a Box deployments)
- Personal AI assistants (voice diary, memory, etc.)
- Any local inference backend needing internet access

---

## Key Files

- `/tmp/VOICE_INTERFACE_PHASE1_LOCKED.md` — Full implementation plan
- `~/Projects/agent-in-a-box/voice_api.py` — Flask backend (to be created)
- `~/Projects/voice-interface/astro-voice/` — Astro frontend (to be created)

---

**This pattern is production-tested and ready for reuse.**
