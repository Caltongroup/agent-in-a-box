/**
 * Voice State Machine
 * Orchestrates the complete voice interaction flow:
 * LISTENING → RECORDING → PROCESSING → TTS_PLAYBACK → LISTENING
 */

import { AudioPipeline } from './AudioPipeline';
import { WakeWordDetector, type DetectionResult } from './WakeWordDetector';
import { SilenceDetector } from './SilenceDetector';

export type VoiceState = 
  | 'LISTENING' 
  | 'WAKE_DETECTED' 
  | 'RECORDING' 
  | 'PROCESSING' 
  | 'TTS_PLAYBACK' 
  | 'ERROR';

export interface VoiceStateMachineConfig {
  wakeThreshold?: number;
  silenceDurationMs?: number;
  maxRecordingMs?: number;
  enableLogging?: boolean;
}

export class VoiceStateMachine {
  private state: VoiceState = 'LISTENING';
  private audioPipeline: AudioPipeline;
  private wakeWordDetector: WakeWordDetector;
  private silenceDetector: SilenceDetector;
  
  private recordedText: string = '';
  private recordingStartTime: number = 0;
  private wakeDetectedTime: number = 0;
  
  private config: Required<VoiceStateMachineConfig>;
  
  // Callbacks
  private onStateChange: ((newState: VoiceState, oldState: VoiceState) => void) | null = null;
  private onTranscript: ((text: string, isFinal: boolean) => void) | null = null;
  private onWakeDetected: (() => void) | null = null;
  private onRecordingStart: (() => void) | null = null;
  private onRecordingEnd: ((text: string) => void) | null = null;
  private onError: ((error: string) => void) | null = null;

  constructor(config?: VoiceStateMachineConfig) {
    this.config = {
      wakeThreshold: config?.wakeThreshold ?? 0.7,
      silenceDurationMs: config?.silenceDurationMs ?? 2500,
      maxRecordingMs: config?.maxRecordingMs ?? 30000,
      enableLogging: config?.enableLogging ?? true
    };

    this.audioPipeline = new AudioPipeline();
    this.wakeWordDetector = new WakeWordDetector();
    this.silenceDetector = new SilenceDetector({
      silenceDurationMs: this.config.silenceDurationMs
    });

    this.log('VoiceStateMachine: Constructor called');
  }

  /**
   * Initialize all components
   */
  async initialize(): Promise<boolean> {
    try {
      this.log('VoiceStateMachine: Initializing...');

      // Initialize audio pipeline
      const audioPipelineOk = await this.audioPipeline.initialize();
      if (!audioPipelineOk) {
        this.error('AudioPipeline initialization failed');
        return false;
      }

      // Initialize wake word detector
      const detectorOk = await this.wakeWordDetector.initialize();
      if (!detectorOk) {
        this.error('WakeWordDetector initialization failed');
        return false;
      }

      // Set up callbacks
      this.setupCallbacks();

      // Start listening
      this.setState('LISTENING');
      this.audioPipeline.startProcessing();

      this.log('VoiceStateMachine: Initialization complete');
      return true;
    } catch (error: any) {
      this.error(`Initialization failed: ${error.message}`);
      return false;
    }
  }

  /**
   * Setup internal callbacks
   */
  private setupCallbacks(): void {
    // Wake word detection
    this.wakeWordDetector.onDetectionCallback((result: DetectionResult) => {
      if (result.phrase === 'Hey Archer' && result.detected) {
        this.handleWakeDetected();
      } else if (result.phrase === 'Go for Archer' && result.detected) {
        this.handleClosePhrase();
      }
    });

    // Audio data processing
    this.audioPipeline.onAudioDataCallback((audioData: Float32Array) => {
      // Process through wake word detector in LISTENING state
      if (this.state === 'LISTENING') {
        this.wakeWordDetector.processAudioChunk(audioData);
      }
      
      // Process through silence detector in RECORDING state
      if (this.state === 'RECORDING') {
        const frequencyData = this.audioPipeline.getFrequencyData();
        if (frequencyData) {
          this.silenceDetector.processFrequencyData(frequencyData);
        }
      }
    });

    // Silence detection (end of speech)
    this.silenceDetector.onSilenceCallback(() => {
      if (this.state === 'RECORDING') {
        this.handleRecordingEnd();
      }
    });

    // Error handling
    this.audioPipeline.onErrorCallback((error: string) => {
      this.error(`AudioPipeline error: ${error}`);
    });

    this.wakeWordDetector.onErrorCallback((error: string) => {
      this.error(`WakeWordDetector error: ${error}`);
    });
  }

  /**
   * Handle wake phrase detected
   */
  private handleWakeDetected(): void {
    if (this.state !== 'LISTENING') {
      return; // Ignore if not listening
    }

    this.log('Wake phrase detected: "Hey Archer"');
    this.wakeDetectedTime = Date.now();
    this.recordedText = '';
    this.setState('RECORDING');
    
    if (this.onWakeDetected) {
      this.onWakeDetected();
    }

    if (this.onRecordingStart) {
      this.onRecordingStart();
    }

    // Reset silence detector for this recording session
    this.silenceDetector.reset();

    this.log('State: LISTENING → RECORDING');
  }

  /**
   * Handle close phrase detected
   */
  private handleClosePhrase(): void {
    if (this.state === 'RECORDING') {
      this.log('Close phrase detected: "Go for Archer"');
      this.handleRecordingEnd();
    }
  }

  /**
   * Handle end of recording (silence or close phrase)
   */
  private handleRecordingEnd(): void {
    if (this.state !== 'RECORDING') {
      return;
    }

    const recordingDuration = Date.now() - this.recordingStartTime;
    this.log(`Recording ended after ${recordingDuration}ms`);
    
    this.setState('PROCESSING');

    if (this.onRecordingEnd) {
      this.onRecordingEnd(this.recordedText);
    }

    // After processing, caller will send text to /chat
    // Then we transition to TTS_PLAYBACK
    // Then back to LISTENING
  }

  /**
   * Called by parent when chat response is received
   */
  async processChatResponse(response: any): Promise<void> {
    if (this.state !== 'PROCESSING') {
      return;
    }

    try {
      this.setState('TTS_PLAYBACK');
      this.log(`TTS playback for: "${response.summary_for_tts || response.full}"`);
      
      // Parent component handles TTS playback
      // When complete, call returnToListening()
    } catch (error: any) {
      this.error(`Failed to process response: ${error.message}`);
      this.returnToListening();
    }
  }

  /**
   * Called after TTS playback completes
   */
  returnToListening(): void {
    this.log('Returning to listening state');
    this.setState('LISTENING');
    this.recordedText = '';
    this.silenceDetector.reset();
  }

  /**
   * Set state and trigger callback
   */
  private setState(newState: VoiceState): void {
    if (newState === this.state) {
      return;
    }

    const oldState = this.state;
    this.state = newState;

    this.log(`State transition: ${oldState} → ${newState}`);

    if (this.onStateChange) {
      this.onStateChange(newState, oldState);
    }

    // Start recording time tracking when entering RECORDING
    if (newState === 'RECORDING') {
      this.recordingStartTime = Date.now();
    }
  }

  /**
   * Get current state
   */
  getState(): VoiceState {
    return this.state;
  }

  /**
   * Update recorded text (called by parent from transcription)
   */
  updateTranscript(text: string, isFinal: boolean): void {
    if (this.state === 'RECORDING') {
      this.recordedText = text;
      if (this.onTranscript) {
        this.onTranscript(text, isFinal);
      }
    }
  }

  /**
   * Register callback for state changes
   */
  onStateChangeCallback(callback: (newState: VoiceState, oldState: VoiceState) => void): void {
    this.onStateChange = callback;
  }

  /**
   * Register callback for transcripts
   */
  onTranscriptCallback(callback: (text: string, isFinal: boolean) => void): void {
    this.onTranscript = callback;
  }

  /**
   * Register callback for wake detection
   */
  onWakeDetectedCallback(callback: () => void): void {
    this.onWakeDetected = callback;
  }

  /**
   * Register callback for recording start
   */
  onRecordingStartCallback(callback: () => void): void {
    this.onRecordingStart = callback;
  }

  /**
   * Register callback for recording end
   */
  onRecordingEndCallback(callback: (text: string) => void): void {
    this.onRecordingEnd = callback;
  }

  /**
   * Register callback for errors
   */
  onErrorCallback(callback: (error: string) => void): void {
    this.onError = callback;
  }

  /**
   * Cleanup
   */
  cleanup(): void {
    this.log('VoiceStateMachine: Cleanup');
    this.audioPipeline.cleanup();
    this.wakeWordDetector.cleanup();
  }

  /**
   * Logging utility
   */
  private log(message: string): void {
    if (this.config.enableLogging) {
      console.log(`[VoiceStateMachine] ${message}`);
    }
  }

  /**
   * Error logging
   */
  private error(message: string): void {
    console.error(`[VoiceStateMachine] ❌ ${message}`);
    this.setState('ERROR');
    if (this.onError) {
      this.onError(message);
    }
  }

  /**
   * Get full state for debugging
   */
  getFullState() {
    return {
      state: this.state,
      recordedText: this.recordedText,
      recordingDuration: this.state === 'RECORDING' ? Date.now() - this.recordingStartTime : 0,
      audioState: this.audioPipeline.getState(),
      detectorState: this.wakeWordDetector.getState(),
      silenceState: this.silenceDetector.getState()
    };
  }
}
