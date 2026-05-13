#!/usr/bin/env python3
"""
Flask backend for voice interface MVP - WIRED VERSION
Serves Astro static files + API endpoints
"""

from flask import Flask, jsonify, request, send_file, send_from_directory, make_response
from summarize import summarize_for_tts, estimate_tts_credits
import os
import io
import subprocess
import json
import re
import time
import threading
from pathlib import Path
from urllib import request as urlrequest
from urllib import error as urlerror

# Serve static files from Astro build output
# Set static_url_path=None to disable automatic Flask static routing
# We handle all routing manually with the SPA catch-all below
app = Flask(__name__, static_folder='static', static_url_path=None)

# Check if ElevenLabs key is available
ELEVENLABS_API_KEY = None
try:
    ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
    if not ELEVENLABS_API_KEY:
        # Try reading from ~/.hermes/.env
        env_file = os.path.expanduser('~/.hermes/.env')
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('ELEVENLABS_API_KEY='):
                        ELEVENLABS_API_KEY = line.split('=', 1)[1].strip()
                        break
    
    # Check if key is valid (not placeholder)
    if ELEVENLABS_API_KEY and (ELEVENLABS_API_KEY == '***' or (not ELEVENLABS_API_KEY.startswith('sk-') and not ELEVENLABS_API_KEY.startswith('sk_'))):
        ELEVENLABS_API_KEY = None
except Exception as e:
    print(f"Warning: Could not load ElevenLabs key: {e}")

def _validate_elevenlabs_key(api_key):
    """Return (is_valid, error_message)."""
    if not api_key:
        return False, 'missing_api_key'

    req = urlrequest.Request(
        'https://api.elevenlabs.io/v1/user',
        headers={'xi-api-key': api_key},
        method='GET',
    )
    try:
        with urlrequest.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return True, None
            return False, f'unexpected_status_{resp.status}'
    except urlerror.HTTPError as e:
        if e.code in {401, 403}:
            return False, 'invalid_api_key'
        return False, f'http_error_{e.code}'
    except Exception as e:
        return False, f'validation_error_{type(e).__name__}'


ELEVENLABS_READY, ELEVENLABS_VALIDATION_ERROR = _validate_elevenlabs_key(ELEVENLABS_API_KEY)

HERMES_ENV_FILE = os.path.expanduser('~/.hermes/.env')
HERMES_SESSIONS_DIR = Path(os.path.expanduser('~/.hermes/sessions'))


def _get_env_or_file(key, default=''):
    value = os.getenv(key)
    if value:
        return value
    if os.path.exists(HERMES_ENV_FILE):
        try:
            with open(HERMES_ENV_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith(f'{key}='):
                        return line.split('=', 1)[1].strip()
        except Exception:
            return default
    return default


TELEGRAM_BOT_TOKEN = _get_env_or_file('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_HOME_CHAT_ID = _get_env_or_file('TELEGRAM_HOME_CHANNEL', '')
if not TELEGRAM_HOME_CHAT_ID:
    TELEGRAM_HOME_CHAT_ID = _get_env_or_file('TELEGRAM_HOME_CHAT_ID', '')

response_queue = []
response_lock = threading.Lock()
session_cursor_file = None
session_cursor_count = 0

voice_diagnostics = []
voice_diagnostics_lock = threading.Lock()


def _enqueue_response(sender, message, source='session'):
    item = {
        'id': f"{int(time.time() * 1000)}-{len(message)}",
        'sender': sender,
        'message': message,
        'source': source,
    }
    with response_lock:
        response_queue.append(item)


def _session_polling_loop():
    global session_cursor_file, session_cursor_count
    while True:
        try:
            if not HERMES_SESSIONS_DIR.exists():
                time.sleep(2)
                continue

            session_files = sorted(
                HERMES_SESSIONS_DIR.glob('session_*.json'),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not session_files:
                time.sleep(2)
                continue

            latest = session_files[0]
            with open(latest, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            messages = session_data.get('messages', [])

            # First pass on a session file should not replay historical backlog.
            if session_cursor_file != str(latest):
                session_cursor_file = str(latest)
                session_cursor_count = len(messages)
                time.sleep(2)
                continue

            if len(messages) > session_cursor_count:
                new_messages = messages[session_cursor_count:]
                for msg in new_messages:
                    role = msg.get('role', '')
                    content = (msg.get('content', '') or '').strip()
                    if role not in {'user', 'assistant'}:
                        continue
                    if len(content) < 2:
                        continue
                    if content.startswith('Review'):
                        continue
                    _enqueue_response('assistant' if role == 'assistant' else 'user', content[:1200])
                session_cursor_count = len(messages)
        except Exception:
            pass
        time.sleep(2)


threading.Thread(target=_session_polling_loop, daemon=True).start()


def _send_to_telegram(message_text):
    if not TELEGRAM_BOT_TOKEN:
        return False, 'TELEGRAM_BOT_TOKEN is not configured'
    if not TELEGRAM_HOME_CHAT_ID:
        return False, 'TELEGRAM_HOME_CHANNEL (or TELEGRAM_HOME_CHAT_ID) is not configured'

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_HOME_CHAT_ID,
        'text': f"UI Message:\n\n{message_text}",
    }

    req = urlrequest.Request(
        api_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('ok'):
                return True, None
            return False, data.get('description', 'Telegram API returned not-ok')
    except urlerror.HTTPError as e:
        return False, f'Telegram HTTP error {e.code}'
    except Exception as e:
        return False, str(e)

# Serve static Astro frontend FIRST (before any middleware interferes)
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_spa(path):
    """Serve Astro static files with SPA fallback to index.html"""
    try:
        # Normalize path: remove trailing slashes
        path_normalized = path.rstrip('/')
        
        if path_normalized:
            full_path = os.path.join(app.static_folder, path_normalized)
            # If it's a directory, serve index.html from it
            if os.path.isdir(full_path):
                target_file = os.path.join(path_normalized, 'index.html')
                return send_from_directory(app.static_folder, target_file)
            # If it's a file, serve it
            if os.path.isfile(full_path):
                return send_from_directory(app.static_folder, path_normalized)
        # Default to root index.html for SPA routing
        return send_from_directory(app.static_folder, 'index.html')
    except Exception as e:
        print(f"SPA error: {e}")
        return send_from_directory(app.static_folder, 'index.html')

# CORS middleware
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        return response
    # For all other requests, let them through (SPA will handle routing)

@app.route('/health', methods=['GET', 'OPTIONS'])
def health():
    return jsonify({
        "status": "ok",
        "service": "voice-api.agentsoul.dev",
        "ready": True,
        "features": ["summarization", "chat", "tts"],
        "browser_compatible": True,
        "tts_ready": ELEVENLABS_READY,
        "tts_mode": "mock" if not ELEVENLABS_READY else "live",
        "tts_validation_error": ELEVENLABS_VALIDATION_ERROR,
        "hermes_gateway": "available",
        "ollama": "127.0.0.1:11434",
        "telegram_bridge": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_HOME_CHAT_ID),
        "sessions_dir": str(HERMES_SESSIONS_DIR),
    })


@app.route('/api/voice/health', methods=['GET', 'OPTIONS'])
def api_voice_health():
    return health()


@app.route('/api/voice/diagnostics', methods=['POST', 'GET', 'OPTIONS'])
def api_voice_diagnostics():
    if request.method == 'OPTIONS':
        return '', 204

    if request.method == 'GET':
        with voice_diagnostics_lock:
            return jsonify({
                'status': 'ok',
                'count': len(voice_diagnostics),
                'latest': voice_diagnostics[-1] if voice_diagnostics else None,
            })

    payload = request.json or {}
    entry = {
        'received_at': int(time.time()),
        'phase': payload.get('phase'),
        'errorsCount': payload.get('errorsCount', 0),
        'isStuck': payload.get('isStuck', False),
    }
    with voice_diagnostics_lock:
        voice_diagnostics.append(entry)
        if len(voice_diagnostics) > 100:
            voice_diagnostics.pop(0)
    return jsonify({'status': 'ok'})


@app.route('/api/send-message', methods=['POST', 'OPTIONS'])
def api_send_message():
    if request.method == 'OPTIONS':
        return '', 204

    data = request.json or {}
    message = (data.get('message', '') or '').strip()
    if not message:
        return jsonify({'success': False, 'error': 'Empty message'}), 400

    sent, error_message = _send_to_telegram(message)
    return jsonify({'success': sent, 'telegram_sent': sent, 'error': error_message})


@app.route('/api/telegram-responses', methods=['GET', 'OPTIONS'])
def api_telegram_responses():
    if request.method == 'OPTIONS':
        return '', 204

    with response_lock:
        messages = response_queue[:]
        response_queue.clear()
    return jsonify({'messages': messages, 'count': len(messages)})

@app.route('/chat', methods=['POST', 'OPTIONS'])
def chat():
    """Chat endpoint - WIRED to Hermes gateway for real LLM responses"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.json or {}
        text = (data.get('text') or data.get('message') or 'No input').strip()
        
        # Call Hermes CLI with -Q (quiet mode) to get just the response
        # Using hermes chat -q "query" --toolsets browser,terminal
        result = subprocess.run(
            ['hermes', 'chat', '-q', text, '--toolsets', 'browser,terminal', '-Q'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            full_response = f"Error calling Hermes gateway: {result.stderr}"
        else:
            full_response = result.stdout.strip()
        
        # Summarize for TTS (reduces costs by 60-75%)
        summary, meta = summarize_for_tts(full_response)
        
        return jsonify({
            "status": "success",
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
    except subprocess.TimeoutExpired:
        return jsonify({
            "status": "error",
            "error": "Hermes gateway timeout (30s)"
        }), 504
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/tts', methods=['POST', 'OPTIONS'])
def tts():
    """TTS endpoint - wired to ElevenLabs for real audio generation"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.json or {}
        text = data.get('text', 'hello')
        voice_id = data.get('voice_id', 'nPczCjzI2devNBz1zQrb')  # Brian - Deep, Resonant and Comforting
        
        if not ELEVENLABS_READY:
            # Return mock WAV with silence for testing
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
        
        # LIVE MODE: Call ElevenLabs API
        import requests
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            audio_io = io.BytesIO(response.content)
            audio_io.seek(0)
            
            return send_file(
                audio_io,
                mimetype="audio/mpeg",
                as_attachment=False,
                download_name="response.mp3"
            )
        else:
            return jsonify({
                "status": "error",
                "error": f"ElevenLabs API error: {response.status_code}",
                "details": response.text
            }), 500
    
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/tts-url', methods=['POST', 'OPTIONS'])
def tts_url():
    """TTS endpoint that returns audio URL instead of binary"""
    if request.method == 'OPTIONS':
        return '', 204
    
    data = request.json or {}
    text = data.get('text', 'hello')
    voice_id = data.get('voice_id', 'default')
    
    return jsonify({
        "audio_url": f"http://127.0.0.1:5001/tts?text={text[:50]}&voice_id={voice_id}",
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
    
    try:
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
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

if __name__ == '__main__':
    print("🎤 Flask Voice API starting...")
    print(f"   Summarization: ✅ Ready")
    print(f"   TTS endpoint: {'✅ Live (ElevenLabs)' if ELEVENLABS_READY else '⚠️ Mock (testing)'}")
    print(f"   Chat endpoint: ✅ Ready")
    print(f"   Static files: ✅ Serving Astro frontend")
    print(f"   Browser CORS: ✅ Enabled")
    app.run(host='0.0.0.0', port=5001, debug=False)
