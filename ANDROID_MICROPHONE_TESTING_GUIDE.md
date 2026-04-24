# Android Microphone Testing Guide

## Quick Test Checklist

### Prerequisites
- Android device (Phone or Tablet)
- Chrome, Firefox, or Samsung Internet browser installed
- voice.agentsoul.dev accessible
- Microphone enabled in device settings

---

## Test Scenario 1: First-Time Permission Flow (✓ Expected to Work)

### Setup
1. On Android device, open browser (Chrome)
2. Navigate to `https://voice.agentsoul.dev`
3. Device should have never visited this site before (or permissions cleared)

### Expected Behavior
1. Page loads with status: "🔄 Checking..."
2. User sees permission prompt: "Allow voice.agentsoul.dev to access your microphone?"
3. User taps "Allow"
4. Microphone status updates to: "✅ Available"
5. Start Recording button becomes active

### Troubleshooting if it fails
- [ ] Check browser console (DevTools: F12) for errors
- [ ] Look for error containing error type: `NotAllowedError`, `NotFoundError`, `NotReadableError`
- [ ] Verify device has microphone (built-in or external)
- [ ] Check if HTTPS certificate is valid (not self-signed)

---

## Test Scenario 2: Permission Previously Denied (✓ Expected Fix)

### Setup
1. On Android device, go to Settings
2. Apps > [Browser Name]
3. Permissions > Microphone > Deny (toggle OFF)
4. Return to voice.agentsoul.dev in browser
5. **WITH FIX**: Should now show "❌ Permission Denied - See settings below"
6. Detailed diagnostic panel displays how to fix

### Expected Behavior (With Our Fix)
1. Page loads
2. Initialization attempts, fails with permission error
3. Microphone status shows: "❌ Permission Denied - See settings below"
4. Yellow warning box appears with title: "🔧 Microphone Permission Fix"
5. Step-by-step instructions show how to re-enable permission in Settings

### Test Steps
1. [ ] User follows on-screen instructions
2. [ ] Opens Settings > Apps > [Browser] > Permissions > Microphone
3. [ ] Toggles Microphone to ON
4. [ ] Returns to browser and refreshes page (F5)
5. [ ] Page should now show "✅ Available" for microphone status
6. [ ] Start Recording button should work

---

## Test Scenario 3: Recording Flow on Android

### Setup
- Microphone permission granted (Scenario 1)
- Page fully loaded with all statuses green

### Test Steps
1. [ ] Click "🎤 Start Recording"
2. [ ] Wait 1 second for state machine to initialize
3. [ ] Say "Hey Archer" (wake phrase)
4. [ ] Console should show: "Wake phrase detected"
5. [ ] Transcription box turns green with "Recording... say your question"
6. [ ] Speak your question (e.g., "What's the weather today?")
7. [ ] Say "Go for Archer" or wait 2.5 seconds of silence
8. [ ] Recording ends, status changes to "Processing"
9. [ ] Request sent to backend
10. [ ] Response received and spoken via TTS
11. [ ] Return to "LISTENING" state

### Expected Errors (If Any)
- If no wake phrase: "Say \"Hey Archer\" to start, or click Start"
- If microphone unavailable: "❌ Microphone unavailable"
- If backend down: "❌ Connection failed"

---

## Test Scenario 4: Constraint Fallback (Android Hardware Compatibility)

### Purpose
Verify that audio constraints gracefully degrade on Android devices with limited audio hardware

### What's Being Tested
```
Attempt 1: echoCancellation + noiseSuppression + sampleRate
    ↓ (If fails on this device)
Attempt 2: sampleRate only
    ↓ (If fails on this device)
Attempt 3: Any microphone
```

### Manual Verification
1. Open browser DevTools (F12)
2. Go to Console tab
3. Observe logs during initialization:
   ```
   AudioPipeline: Attempting getUserMedia with constraint set 1: {...}
   ✓ AudioPipeline: Microphone access granted (constraint 1)
   ```
4. Note which constraint set succeeded (0=strict, 1=reduced, 2=minimal, 3=any)
5. On Android: Expect constraint 1, 2, or 3
6. On Desktop: Expect constraint 0

### Test on Multiple Devices
- [ ] Pixel 6/7 (Modern) → Expect constraint 0-1
- [ ] OnePlus/Xiaomi (Mid-range) → Expect constraint 1-2
- [ ] Budget Android (Old hardware) → Expect constraint 2-3

---

## Test Scenario 5: Error Recovery

### Test 5A: Microphone Permission Revoked During Recording
1. Start recording ("Hey Archer")
2. While recording, go to Settings and disable microphone permission
3. Return to browser
4. Expected: Recording stops, error message shows "Permission denied"

### Test 5B: Close Browser/App in Middle of Recording
1. Start recording
2. Close browser completely
3. Reopen browser and return to page
4. Expected: State resets to LISTENING, no crash

### Test 5C: Multiple Simultaneous Requests
1. Click Start Recording multiple times rapidly
2. Expected: Only one recording session active, others ignored

---

## Test Scenario 6: Cross-Browser Testing (Android)

### Chrome (Most Common)
- [ ] Permission prompt appears
- [ ] Microphone initialization succeeds after permission granted
- [ ] Recording and transcription work
- [ ] TTS playback works

### Firefox (Android)
- [ ] Same as Chrome
- [ ] May have slightly different permission UI

### Samsung Internet (Samsung Devices)
- [ ] May require additional permission in Samsung account settings
- [ ] Generally has better audio codec support
- [ ] Verify recording quality is good

---

## Test Scenario 7: iOS Safari (Bonus Cross-Platform)

### Setup
- iPhone with iOS 14+
- Safari browser
- voice.agentsoul.dev bookmarked

### Expected Behavior
1. Page loads
2. Safari may show permission prompt differently (system-level)
3. User allows microphone access
4. Recording and transcription should work
5. TTS playback via system audio

### Known iOS Issues
- [ ] Web Speech API may be limited in scope
- [ ] SpeechRecognition might not support continuous mode
- [ ] May need to manually stop recording

---

## Debugging: Console Commands

### Check Current Diagnostics
```javascript
// In browser console (F12 > Console tab)
import { AndroidMicrophoneHelper } from './lib/AndroidMicrophoneHelper.ts';
await AndroidMicrophoneHelper.getDiagnosticMessage();
```

### Check Audio Pipeline State
```javascript
// Should be called from VoiceStateMachine context
stateMachine.getFullState();
// Returns: {state, audioState, detectorState, etc.}
```

### Check Permission Status
```javascript
const result = await navigator.permissions.query({name: 'microphone'});
console.log('Microphone permission:', result.state); // 'granted'|'denied'|'prompt'
```

### View All Console Logs
1. Open DevTools: F12
2. Go to Console tab
3. Filter by `AudioPipeline`, `VoiceStateMachine`, `AndroidMicrophoneHelper`
4. Look for error messages and constraint attempts

---

## Performance Metrics to Track

### Audio Initialization Time
- Expected: < 1000ms on Android
- Alert if: > 3000ms (may indicate device issues)

### Constraint Fallback Attempts
- Desktop: Should succeed on attempt 0
- Android: Should succeed on attempt 1-2

### Permission Status Query Time
- Expected: < 100ms
- Alert if: > 500ms (permission system slow)

---

## Known Limitations & Workarounds

### Limitation 1: Android Permissions Cascade
**Problem**: If user denies at any level (app, browser, site), all fail silently  
**Workaround**: Show diagnostic panel with step-by-step fix instructions ✓ (Implemented)

### Limitation 2: Audio Hardware Varies Greatly
**Problem**: Each Android device has different audio codec support  
**Workaround**: Graceful constraint fallback (0 → 1 → 2 → 3) ✓ (Implemented)

### Limitation 3: Web Speech API Quality on Android
**Problem**: Recognition accuracy lower on some devices  
**Workaround**: Manual fallback button for text input (Future enhancement)

### Limitation 4: TTS Audio Policy
**Problem**: Some Android devices require user gesture to play audio  
**Workaround**: Show "Play Response" button if auto-play fails (Future enhancement)

---

## Success Criteria

✅ **Test Complete When**:
1. Permission prompt appears on first visit
2. Microphone status shows "✅ Available" after permission granted
3. Recording begins with "Hey Archer" wake phrase
4. Transcription updates in real-time
5. Response is received and TTS plays
6. State returns to LISTENING after playback
7. No JavaScript errors in console
8. Works on Chrome, Firefox, and Samsung Internet on Android
9. Permission denied scenario shows helpful fix UI
10. Device-specific audio constraints handled gracefully

---

## Bug Report Template

If you encounter an issue, please report:

```
Device: [Model, e.g., Pixel 6, OnePlus 9]
OS: Android [Version]
Browser: [Chrome/Firefox/Samsung Internet]
URL: https://voice.agentsoul.dev

Issue: [Describe what went wrong]

Browser Console Output (F12 > Console):
[Paste relevant logs here]

Expected Behavior:
[What should happen]

Actual Behavior:
[What actually happened]

Diagnostic Info (from page):
Microphone Status: [value]
Permission Status: [granted/denied/prompt]
Platform: [Android/iOS]
```

---

## Deployment Checklist

Before deploying AudioPipeline.ts changes:

- [ ] AudioPipeline.ts enhanced with Android constraints
- [ ] AndroidMicrophoneHelper.ts created and tested
- [ ] VoiceInterface.astro updated with permission error UI
- [ ] Console logs added for diagnostics
- [ ] Permission pre-flight check implemented
- [ ] Error messages user-friendly
- [ ] Tested on real Android device (not emulator)
- [ ] Tested permission denied scenario
- [ ] Tested cross-browser (Chrome, Firefox, Samsung Internet)
- [ ] No regressions on Desktop/iOS
- [ ] Documentation updated

---
