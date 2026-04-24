# Android Microphone Initialization Failure Diagnostic Report

**Date**: 2024  
**Issue**: VoiceStateMachine → AudioPipeline → `getUserMedia()` failing silently on Android Chrome  
**Environment**: voice.agentsoul.dev (production HTTPS)  
**Impact**: No permission prompt, microphone state shows "Available" but initialization fails  
**Affected Users**: Android phone users attempting to use voice interface MVP

---

## Root Cause Analysis

### 1. **Problem Identification**
- **Symptom**: No permission prompt appears on Android
- **Silent Failure**: AudioPipeline.initialize() returns `false` without user-facing error
- **State**: Web Audio API context created, but `getUserMedia()` fails before mic access request
- **Code Path**: 
  ```
  VoiceStateMachine.initialize() 
  → AudioPipeline.initialize() 
  → navigator.mediaDevices.getUserMedia() [FAILS HERE]
  ```

### 2. **Why getUserMedia() Fails on Android**

#### A. **HTTPS Requirement** ✓ Met
- voice.agentsoul.dev is HTTPS
- getUserMedia requires HTTPS (or localhost)
- Not the issue here

#### B. **Permission Status Denied** ⚠️ Likely Issue
Android Chrome maintains permission state per site:
- If user denied mic access previously → getUserMedia() silently fails
- Permission dialog may not show if:
  - Previously denied (need Settings reset)
  - Microphone disabled globally on device
  - App/browser permissions misconfigured

#### C. **Device Permissions Not Granted** ⚠️ Likely Issue
Android requires:
1. **App-level permission**: Chrome has microphone permission in Android settings
2. **Browser-level permission**: User approves when prompted
3. **Feature-level request**: `getUserMedia()` specific to voice.agentsoul.dev

If ANY level is denied → silent failure with no visible prompt

#### D. **Browser Compatibility** ⚠️ Issue Found
- Chrome on Android: ✓ Full support (if permissions granted)
- Firefox on Android: ✓ Support
- Samsung Internet: ✓ Support  
- Issue: VoiceInterface uses Web Audio API + Web Speech API combo that may fail if permissions cascade incorrectly

#### E. **Audio Context State** ⚠️ Issue Found
Current code:
```typescript
// AudioPipeline.ts line 40-43
if (this.audioContext.state === 'suspended') {
  await this.audioContext.resume();
}
```

**Problem**: On Android, AudioContext may fail to resume if:
- No user gesture (getUSERMedia needs prior user interaction)
- Audio policy violations
- Event handlers not properly configured

---

## Current Implementation Issues

### AudioPipeline.ts Analysis
**Line 46-53**: getUserMedia() call lacks Android-specific error handling
```typescript
this.mediaStream = await navigator.mediaDevices.getUserMedia({
  audio: {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: false,
    sampleRate: { ideal: 16000 }
  }
});
```

**Issues**:
1. ❌ No fallback for Android audio constraints
2. ❌ `echoCancellation` + `noiseSuppression` may fail on some Android devices
3. ❌ `sampleRate: {ideal: 16000}` not supported on all Android audio hardware
4. ❌ Error caught but not logged with specifics (line 87-94)

### VoiceInterface.astro Analysis
**Line 105-112**: Initialization failure not handled gracefully
```typescript
const smOk = await stateMachine.initialize();
if (!smOk) {
  console.error('VoiceStateMachine initialization failed');
  updateStatus('connection', '❌ Failed to initialize');
  return; // Silent exit
}
```

**Issues**:
1. ❌ User sees "Failed to initialize" without diagnostic info
2. ❌ No permission status check before attempting initialization
3. ❌ No fallback UI to debug or reset permissions
4. ❌ Web Speech API used as fallback but never verified for Android

---

## Diagnostic Findings

### Missing Diagnostic Layer
The code lacks visibility into **why** getUserMedia() fails:

```
What we get:    ❌ "AudioPipeline: Initialization failed"
What we need:   🔍 "Permission denied: 'microphone' | NotAllowedError | NotFoundError | etc."
```

### Permission Status API Gap
Current code doesn't check:
```typescript
// MISSING: Permission status check
const permStatus = await navigator.permissions.query({name: 'microphone'});
console.log('Microphone permission:', permStatus.state); // 'granted'|'denied'|'prompt'
```

This would instantly show:
- ✓ `granted` → Proceed (but still fails?)
- ✗ `denied` → User must reset in Settings
- ⚠️ `prompt` → Should trigger dialog

---

## Android-Specific Constraints

### What Works on Android Chrome
✓ getUserMedia with basic audio config  
✓ Web Audio API (AudioContext, AnalyserNode, etc.)  
✓ Web Speech API (SpeechRecognition)  

### What Fails on Android Chrome
✗ Stacked audio constraints (echoCancellation + noiseSuppression + sampleRate) on some hardware  
✗ ScriptProcessorNode (deprecated, replaced with AudioWorklet on modern browsers)  
✗ Permissions cascade (one denied = all silent fail)  

### Device-Specific Issues
- **OnePlus/Xiaomi**: Audio hardware may not support requested sample rates
- **Samsung**: May require Samsung Internet for full support
- **Stock Android**: Limited audio hardware capability

---

## Solution Strategy

### Phase 1: Diagnostic Enhancement ✅
Add detailed error reporting to identify exact failure point:
```typescript
// AudioPipeline.ts enhancement
catch (error: any) {
  const errorType = error.name; // NotAllowedError, NotFoundError, etc.
  const errorMsg = `[${errorType}] ${error.message}`;
  console.error('AudioPipeline: Initialization failed', {
    errorType,
    errorMsg,
    userAgent: navigator.userAgent,
    mediaDevicesSupported: !!navigator.mediaDevices,
    getUserMediaSupported: !!navigator.mediaDevices?.getUserMedia
  });
}
```

### Phase 2: Permission Pre-Flight Check ✅
Verify permissions before getUserMedia():
```typescript
async checkMicrophonePermission(): Promise<'granted'|'denied'|'prompt'> {
  if (!navigator.permissions?.query) {
    return 'prompt'; // Fallback for older browsers
  }
  
  const result = await navigator.permissions.query({name: 'microphone'});
  console.log('Microphone permission status:', result.state);
  return result.state;
}
```

### Phase 3: Graceful Fallback Strategy ✅
Implement constraint fallback for Android:
```typescript
// Try strict constraints first (desktop)
// Fall back to minimal constraints (Android)
const constraints = [
  {audio: {echoCancellation: true, noiseSuppression: true, sampleRate: {ideal: 16000}}}, // Desktop
  {audio: {sampleRate: {ideal: 16000}}}, // Android - minimal
  {audio: {}}  // Last resort - any microphone
];

for (let constraint of constraints) {
  try {
    this.mediaStream = await navigator.mediaDevices.getUserMedia(constraint);
    console.log('✓ Audio initialized with constraint:', constraint);
    break;
  } catch (e) {
    console.warn('✗ Constraint failed:', constraint, e.name);
  }
}
```

### Phase 4: User-Facing Diagnostics UI ✅
Show actionable errors:
```typescript
if (error.name === 'NotAllowedError') {
  // Permission denied
  showUI('Please grant microphone permission in Settings');
} else if (error.name === 'NotFoundError') {
  // No microphone device
  showUI('No microphone found. Check device settings.');
} else if (error.name === 'NotReadableError') {
  // Microphone in use/blocked
  showUI('Microphone is unavailable. Try restarting browser.');
}
```

---

## Implementation Plan

### File: AudioPipeline.ts
**Changes Required**:
1. Add permission pre-flight check
2. Implement constraint fallback mechanism
3. Enhanced error reporting with error types
4. Support for both Web Audio API and fallback modes

### File: VoiceInterface.astro
**Changes Required**:
1. Capture error details from AudioPipeline
2. Show user-facing diagnostic UI
3. Add "Fix Permissions" button that opens settings guide
4. Offer browser detection + compatibility info

### New File: AndroidMicrophoneHelper.ts
**Purpose**: Android-specific utility for permission handling

---

## Testing Checklist

### Android Chrome
- [ ] Device: Pixel 6/7 (modern)
- [ ] Device: OnePlus/Xiaomi (mid-range)
- [ ] Scenario 1: First visit (permission prompt)
- [ ] Scenario 2: Permission granted (should work)
- [ ] Scenario 3: Permission denied previously (show fix UI)
- [ ] Scenario 4: Microphone disabled in device settings

### Android Firefox
- [ ] First visit permission flow
- [ ] Microphone access after permission granted

### iOS Safari
- [ ] Permission prompt
- [ ] Successful initialization

### Error Scenarios
- [ ] No microphone device
- [ ] Microphone already in use (other app)
- [ ] Audio context creation fails
- [ ] Network timeout to backend

---

## Expected Outcomes

After implementation:
✅ Clear error messages telling users **exactly** what's wrong  
✅ Automatic fallback to minimal constraints on Android  
✅ Permission pre-flight check before attempting access  
✅ "Fix microphone" guide for users who denied permission  
✅ Cross-browser, cross-device testing validation  

---

## References

- [MDN: getUserMedia()](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
- [MDN: Permissions API](https://developer.mozilla.org/en-US/docs/Web/API/Permissions_API)
- [Web Audio API Android Support](https://caniuse.com/audio-api)
- [Chrome Android Audio Permissions](https://developer.chrome.com/articles/audio-microphone-permissions/)
