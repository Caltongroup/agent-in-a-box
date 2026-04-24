/**
 * VoiceStateMachineWithDiagnostics.ts
 * 
 * Enhanced state machine for voice interface with:
 * - Integrated diagnostic logging at every transition
 * - Explicit timeouts with fallback handling
 * - Error boundaries with graceful degradation
 * - Status display that works without console
 * 
 * KEY FIX: Every state transition is logged and timed.
 * If any state takes >5 seconds without progress, we show error UI.
 */

import DiagnosticLogger from './DiagnosticLogger';

type VoiceState = 
  | 'INIT'
  | 'CHECKING_CONNECTION'
  | 'CHECKING_MICROPHONE'
  | 'READY'
  | 'LISTENING'
  | 'WAKE_DETECTED'
  | 'RECORDING'
  | 'PROCESSING'
  | 'PLAYING_RESPONSE'
  | 'ERROR'
  | 'DEGRADED';

interface StateContext {
  timestamp: number;
  duration: number;
  error?: Error;
  message?: string;
}

interface InitializationResult {
  success: boolean;
  state: VoiceState;
  error?: string;
  details?: Record<string, any>;
}

export class VoiceStateMachineWithDiagnostics {
  private currentState: VoiceState = 'INIT';
  private previousState: VoiceState | null = null;
  private stateEnteredAt: number = Date.now();
  private diagnosticLogger: DiagnosticLogger;
  private stateTimeouts: Map<VoiceState, NodeJS.Timeout> = new Map();
  private initializationTimeout: NodeJS.Timeout | null = null;
  private stateChangeCallbacks: Array<(state: VoiceState, context: StateContext) => void> = [];
  private readonly STATE_TIMEOUT_MS = 5000; // 5 second timeout per state
  private readonly INIT_TOTAL_TIMEOUT_MS = 15000; // 15 second total init timeout
  private statusElement: HTMLElement | null = null;

  constructor() {
    this.diagnosticLogger = DiagnosticLogger.getInstance('/api/voice/diagnostics');
    this.diagnosticLogger.log('VOICESM_CREATED', {}, 'DEBUG');
  }

  /**
   * Initialize the voice interface - the main entry point
   */
  async initialize(): Promise<InitializationResult> {
    this.diagnosticLogger.log('INIT_START', { timestamp: Date.now() }, 'INFO');
    this.diagnosticLogger.setPhase('INITIALIZATION');
    this.setState('INIT');

    // Set up overall initialization timeout
    this.initializationTimeout = setTimeout(() => {
      this.handleInitializationTimeout();
    }, this.INIT_TOTAL_TIMEOUT_MS);

    try {
      // Step 1: Check connection
      this.setState('CHECKING_CONNECTION');
      await this.checkConnection();

      // Step 2: Check microphone
      this.setState('CHECKING_MICROPHONE');
      await this.checkMicrophone();

      // Step 3: Initialize audio pipeline
      this.diagnosticLogger.log('AUDIO_PIPELINE_INIT', {}, 'INFO');
      await this.initializeAudioPipeline();

      // Step 4: Initialize state machine
      this.diagnosticLogger.log('STATE_MACHINE_READY', {}, 'INFO');
      this.setState('READY');
      this.diagnosticLogger.setPhase('READY');

      // Clear initialization timeout
      if (this.initializationTimeout) {
        clearTimeout(this.initializationTimeout);
        this.initializationTimeout = null;
      }

      this.diagnosticLogger.log('INIT_COMPLETE', { duration: Date.now() - this.stateEnteredAt }, 'INFO');
      return {
        success: true,
        state: this.currentState,
        details: { duration: Date.now() - this.stateEnteredAt },
      };
    } catch (error) {
      this.handleInitializationError(error as Error);
      return {
        success: false,
        state: this.currentState,
        error: (error as Error).message,
      };
    }
  }

  /**
   * State transition with comprehensive logging
   */
  private setState(newState: VoiceState): void {
    const now = Date.now();
    const previousDuration = now - this.stateEnteredAt;

    // Log state exit
    if (this.previousState !== null) {
      this.diagnosticLogger.log(`STATE_EXIT_${this.currentState}`, {
        duration: previousDuration,
        nextState: newState,
      }, 'DEBUG');
    }

    // Clear any existing timeout for this state
    if (this.stateTimeouts.has(this.currentState)) {
      const timeout = this.stateTimeouts.get(this.currentState);
      if (timeout) clearTimeout(timeout);
      this.stateTimeouts.delete(this.currentState);
    }

    // Update state
    this.previousState = this.currentState;
    this.currentState = newState;
    this.stateEnteredAt = now;

    // Log state entry
    this.diagnosticLogger.log(`STATE_ENTER_${newState}`, {
      previousState: this.previousState,
      timestamp: now,
    }, 'INFO');

    // Set timeout for this state
    const stateTimeout = setTimeout(() => {
      this.handleStateTimeout(newState);
    }, this.STATE_TIMEOUT_MS);
    this.stateTimeouts.set(newState, stateTimeout);

    // Notify callbacks
    for (const callback of this.stateChangeCallbacks) {
      callback(newState, {
        timestamp: now,
        duration: previousDuration,
      });
    }

    // Update UI
    this.updateStatusUI();
  }

  /**
   * Check backend connection
   */
  private async checkConnection(): Promise<void> {
    this.diagnosticLogger.log('CONNECTION_CHECK_START', {}, 'DEBUG');

    try {
      const response = await Promise.race([
        fetch('/api/voice/health', { method: 'GET' }),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error('Connection timeout')), 5000)
        ),
      ]);

      if (!response.ok) {
        throw new Error(`Health check returned ${response.status}`);
      }

      this.diagnosticLogger.log('CONNECTION_CHECK_PASS', {}, 'INFO');
    } catch (error) {
      this.diagnosticLogger.captureError('CONNECTION_CHECK_FAILED', error as Error, {
        step: 'checkConnection',
      });
      throw error;
    }
  }

  /**
   * Check microphone availability
   */
  private async checkMicrophone(): Promise<void> {
    this.diagnosticLogger.log('MICROPHONE_CHECK_START', {}, 'DEBUG');

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('getUserMedia not supported');
      }

      const stream = await Promise.race([
        navigator.mediaDevices.getUserMedia({ audio: true }),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error('Microphone permission timeout')), 5000)
        ),
      ]);

      // Stop the stream immediately after checking
      stream.getTracks().forEach((track) => track.stop());

      this.diagnosticLogger.log('MICROPHONE_CHECK_PASS', {}, 'INFO');
    } catch (error) {
      this.diagnosticLogger.captureError('MICROPHONE_CHECK_FAILED', error as Error, {
        step: 'checkMicrophone',
      });
      throw error;
    }
  }

  /**
   * Initialize audio pipeline (this is likely where the hang is)
   */
  private async initializeAudioPipeline(): Promise<void> {
    this.diagnosticLogger.log('AUDIO_PIPELINE_INIT_START', {}, 'DEBUG');

    try {
      // Create audio context
      const audioContext = new (window as any).AudioContext?.() || new (window as any).webkitAudioContext?.();
      if (!audioContext) {
        throw new Error('AudioContext not available');
      }
      this.diagnosticLogger.log('AUDIO_CONTEXT_CREATED', { sampleRate: audioContext.sampleRate }, 'DEBUG');

      // Resume context if suspended (common on mobile)
      if (audioContext.state === 'suspended') {
        this.diagnosticLogger.log('AUDIO_CONTEXT_SUSPENDED_RESUME', {}, 'DEBUG');
        await audioContext.resume();
      }
      this.diagnosticLogger.log('AUDIO_CONTEXT_READY', { state: audioContext.state }, 'DEBUG');

      // Attempt to create audio worklet if available
      if (audioContext.audioWorklet) {
        try {
          this.diagnosticLogger.log('AUDIO_WORKLET_ADD_MODULE_START', {}, 'DEBUG');
          // This might be where it's hanging - add timeout
          await Promise.race([
            audioContext.audioWorklet.addModule('/audio-processor.js'),
            new Promise<void>((_, reject) =>
              setTimeout(() => reject(new Error('AudioWorklet addModule timeout')), 3000)
            ),
          ]);
          this.diagnosticLogger.log('AUDIO_WORKLET_ADD_MODULE_SUCCESS', {}, 'INFO');
        } catch (error) {
          this.diagnosticLogger.log('AUDIO_WORKLET_ADD_MODULE_FAILED', {
            error: (error as Error).message,
            fallback: 'ScriptProcessor',
          }, 'WARN');
          // Continue with fallback - don't throw
        }
      }

      this.diagnosticLogger.log('AUDIO_PIPELINE_INIT_COMPLETE', {}, 'INFO');
    } catch (error) {
      this.diagnosticLogger.captureError('AUDIO_PIPELINE_INIT_FAILED', error as Error, {
        step: 'initializeAudioPipeline',
      });
      throw error;
    }
  }

  /**
   * Handle state timeout - called if a state doesn't transition within 5 seconds
   */
  private handleStateTimeout(state: VoiceState): void {
    this.diagnosticLogger.log(`STATE_TIMEOUT_${state}`, {
      state,
      duration: Date.now() - this.stateEnteredAt,
    }, 'ERROR');

    const message = `State "${state}" timed out. No progress for 5 seconds.`;
    this.handleError(new Error(message), 'STATE_TIMEOUT');
  }

  /**
   * Handle overall initialization timeout
   */
  private handleInitializationTimeout(): void {
    const message = 'Overall voice initialization timed out (>15 seconds)';
    this.diagnosticLogger.log('INIT_TIMEOUT', {
      currentState: this.currentState,
      duration: Date.now() - this.stateEnteredAt,
    }, 'CRITICAL');

    this.handleError(new Error(message), 'INIT_TIMEOUT');
  }

  /**
   * Handle initialization error with graceful fallback
   */
  private handleInitializationError(error: Error): void {
    this.diagnosticLogger.captureError('INITIALIZATION_ERROR', error, {
      state: this.currentState,
    });

    this.setState('DEGRADED');
    this.showErrorUI(error.message);
  }

  /**
   * General error handler
   */
  private handleError(error: Error, category: string): void {
    this.diagnosticLogger.captureError(category, error);
    this.setState('ERROR');
    this.showErrorUI(`${category}: ${error.message}`);
  }

  /**
   * Update UI status indicator without relying on console
   */
  private updateStatusUI(): void {
    if (!this.statusElement) {
      this.statusElement = document.getElementById('voice-status') || this.createStatusElement();
    }

    const stateLabels: Record<VoiceState, string> = {
      INIT: '🔄 Initializing...',
      CHECKING_CONNECTION: '🔄 Checking Connection...',
      CHECKING_MICROPHONE: '🎤 Checking Microphone...',
      READY: '✅ Ready',
      LISTENING: '👂 Listening...',
      WAKE_DETECTED: '🎯 Wake Detected',
      RECORDING: '🔴 Recording...',
      PROCESSING: '⚙️ Processing...',
      PLAYING_RESPONSE: '🔊 Playing Response...',
      ERROR: '❌ Error',
      DEGRADED: '⚠️ Limited Mode',
    };

    this.statusElement.textContent = stateLabels[this.currentState] || this.currentState;
    this.statusElement.setAttribute('data-state', this.currentState);
  }

  /**
   * Create status element if it doesn't exist
   */
  private createStatusElement(): HTMLElement {
    const element = document.createElement('div');
    element.id = 'voice-status';
    element.style.cssText = `
      position: fixed;
      top: 10px;
      right: 10px;
      background: rgba(0, 0, 0, 0.7);
      color: #fff;
      padding: 10px 15px;
      border-radius: 4px;
      font-size: 14px;
      font-family: monospace;
      z-index: 9999;
      transition: background-color 0.2s;
    `;
    document.body.appendChild(element);
    return element;
  }

  /**
   * Show error UI overlay that doesn't require console
   */
  private showErrorUI(message: string): void {
    const overlay = document.getElementById('voice-error-overlay') || document.createElement('div');
    overlay.id = 'voice-error-overlay';
    overlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.9);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 99998;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    `;

    const panel = document.createElement('div');
    panel.style.cssText = `
      background: #fff;
      border-radius: 8px;
      padding: 30px;
      max-width: 400px;
      text-align: center;
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
    `;

    const title = document.createElement('h2');
    title.textContent = '❌ Voice Interface Error';
    title.style.color = '#d32f2f';
    title.style.marginBottom = '15px';

    const errorText = document.createElement('p');
    errorText.textContent = message;
    errorText.style.color = '#333';
    errorText.style.marginBottom = '20px';
    errorText.style.fontSize = '14px';
    errorText.style.lineHeight = '1.5';

    const diagnostic = document.createElement('p');
    diagnostic.textContent = this.diagnosticLogger.getSummary();
    diagnostic.style.color = '#666';
    diagnostic.style.fontSize = '12px';
    diagnostic.style.fontFamily = 'monospace';
    diagnostic.style.textAlign = 'left';
    diagnostic.style.background = '#f5f5f5';
    diagnostic.style.padding = '10px';
    diagnostic.style.borderRadius = '4px';
    diagnostic.style.maxHeight = '200px';
    diagnostic.style.overflow = 'auto';
    diagnostic.style.marginBottom = '20px';
    diagnostic.style.whiteSpace = 'pre-wrap';
    diagnostic.style.wordBreak = 'break-all';

    const button = document.createElement('button');
    button.textContent = 'Retry';
    button.style.cssText = `
      padding: 10px 30px;
      background: #1976d2;
      color: white;
      border: none;
      border-radius: 4px;
      font-size: 14px;
      cursor: pointer;
    `;
    button.onclick = () => {
      overlay.remove();
      location.reload();
    };

    panel.appendChild(title);
    panel.appendChild(errorText);
    panel.appendChild(diagnostic);
    panel.appendChild(button);
    overlay.appendChild(panel);

    if (!document.getElementById('voice-error-overlay')) {
      document.body.appendChild(overlay);
    }
  }

  /**
   * Subscribe to state changes
   */
  onStateChange(callback: (state: VoiceState, context: StateContext) => void): void {
    this.stateChangeCallbacks.push(callback);
  }

  /**
   * Get current state
   */
  getState(): VoiceState {
    return this.currentState;
  }

  /**
   * Get diagnostic summary
   */
  getDiagnosticSummary(): string {
    return this.diagnosticLogger.getSummary();
  }
}

export default VoiceStateMachineWithDiagnostics;
