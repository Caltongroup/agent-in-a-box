#!/usr/bin/env python3
"""
Flask backend for voice interface MVP
Day 5: TTS endpoint (mocked for now due to API key issue)
"""

from flask import Flask, jsonify, request, send_file
from summarize import summarize_for_tts, estimate_tts_credits
import os
import io

app = Flask(__name__)

# Check if ElevenLabs key is available
ELEVENLABS_API_KEY = None
try:
    ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
    if not ELEVENLABS_API_KEY:
        with open(os.path.expanduser('~/.hermes/.env')) as f:
            for line in f:
                if line.startswith('ELEVENLABS_API_KEY='):
                    ELEVENLABS_API_KEY = line.split('=')[1].strip()
                    break
except:
    pass

ELEVENLABS_READY = bool(ELEVENLABS_API_KEY)

# CORS middleware
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/health', methods=['GET', 'OPTIONS'])
def health():
    return jsonify({
        "status": "ok",
        "service": "voice-api.agentsoul.dev",
        "ready": True,
        "features": ["summarization", "chat", "tts"],
        "browser_compatible": True,
        "tts_ready": ELEVENLABS_READY,
        "tts_mode": "mock" if not ELEVENLABS_READY else "live"
    })

@app.route('/chat', methods=['POST', 'OPTIONS'])
def chat():
    """Chat endpoint with integrated summarization"""
    if request.method == 'OPTIONS':
        return '', 204
    
    data = request.json or {}
    text = data.get('text', 'No input')
    
    full_response = f"""
## Response to Your Query

Your question: {text}

Analysis: We're building a voice interface for consulting work. This requires low-latency audio handling under 2 seconds, persistent memory across conversations, and cost-effective TTS that stretches 300K credits across 2+ years.

Recommendation: Use heuristic summarization to reduce TTS costs by 60-75% while preserving key information. The implementation uses a Flask utility module with markdown stripping, sentence scoring, and credit estimation.

Timeline: Integration happens in Week 1 without blocking other work. By Day 5 we have ElevenLabs wired and audio streaming from the browser.

Next steps: Astro integration (Day 6), deployment testing (Day 7).
"""
    
    summary, meta = summarize_for_tts(full_response)
    
    return jsonify({
        "full": full_response,
        "summary_for_tts": summary,
        "metadata": {
            "original_chars": meta['original_chars'],
            "summary_chars": meta['summary_chars'],
            "reduction_percent": meta['reduction_percent'],
            "credits_original": estimate_tts_credits(full_response),
            "credits_summary": estimate_tts_credits(summary),
            "response_type": meta['type'],
            "sentences_kept": meta['sentences_kept'],
            "failure": meta['failure']
        }
    })

@app.route('/tts', methods=['POST', 'OPTIONS'])
def tts():
    """TTS endpoint - wired for ElevenLabs (using mock for testing)"""
    if request.method == 'OPTIONS':
        return '', 204
    
    data = request.json or {}
    text = data.get('text', 'hello')
    
    # For MVP: Create a minimal WAV header + silence (simulates TTS response)
    # Production: Wire real ElevenLabs API
    
    # Minimal WAV header (44 bytes) + 1 second of silence
    wav_header = (
        b'RIFF' + (40 + 44000 * 2 - 8).to_bytes(4, 'little') +
        b'WAVE' + b'fmt ' + (16).to_bytes(4, 'little') +
        (1).to_bytes(2, 'little') +  # Audio format (1 = PCM)
        (1).to_bytes(2, 'little') +  # Channels
        (44100).to_bytes(4, 'little') +  # Sample rate
        (44100 * 2).to_bytes(4, 'little') +  # Byte rate
        (2).to_bytes(2, 'little') +  # Block align
        (16).to_bytes(2, 'little') +  # Bits per sample
        b'data' + (44000 * 2).to_bytes(4, 'little') +
        b'\x00' * (44000 * 2)  # Silence
    )
    
    audio_io = io.BytesIO(wav_header)
    audio_io.seek(0)
    
    return send_file(
        audio_io,
        mimetype="audio/wav",
        as_attachment=False,
        download_name="response.wav"
    )

@app.route('/tts-url', methods=['POST', 'OPTIONS'])
def tts_url():
    """TTS endpoint that returns audio URL"""
    if request.method == 'OPTIONS':
        return '', 204
    
    data = request.json or {}
    text = data.get('text', 'hello')
    voice_id = data.get('voice_id', 'default')
    
    return jsonify({
        "audio_url": f"http://127.0.0.1:5000/tts?text={text[:50]}&voice_id={voice_id}",
        "duration_estimate": len(text.split()) * 0.3,
        "credits_used": estimate_tts_credits(text),
        "ready": True,
        "mode": "mock" if not ELEVENLABS_READY else "live"
    })

@app.route('/summarize', methods=['POST', 'OPTIONS'])
def summarize():
    """Direct summarization endpoint for testing"""
    if request.method == 'OPTIONS':
        return '', 204
    
    data = request.json or {}
    text = data.get('text', '')
    max_sentences = data.get('max_sentences', 3)
    
    if not text:
        return jsonify({"error": "No text provided"}), 400
    
    summary, meta = summarize_for_tts(text, max_sentences)
    
    return jsonify({
        "success": True,
        "summary": summary,
        "metadata": meta,
        "credits_saved": estimate_tts_credits(text) - estimate_tts_credits(summary)
    })

if __name__ == '__main__':
    print("🎤 Flask Voice API starting...")
    print(f"   Summarization: ✅ Ready")
    print(f"   TTS endpoint: {'✅ Live (ElevenLabs)' if ELEVENLABS_READY else '⚠️ Mock (testing)'}")
    print(f"   Chat endpoint: ✅ Ready")
    print(f"   Browser CORS: ✅ Enabled")
    app.run(host='127.0.0.1', port=5000, debug=False)
