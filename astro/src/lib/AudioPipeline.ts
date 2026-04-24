/**
 * Audio Pipeline Module (Android-Compatible)
 * Handles continuous audio streaming, noise suppression, and real-time processing
 * Uses Web Audio API for low-latency audio capture and processing
 * 
 * Android Enhancements:
 * - Permission pre-flight checks using Permissions API
 * - Graceful constraint fallback for Android devices
 * - Detailed error reporting with diagnostic context
 */

export class AudioPipeline {
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private analyserNode: AnalyserNode | null = null;
  private scriptProcessor: ScriptProcessorNode | null = null;
  private gainNode: GainNode | null = null;
  
  // Callbacks
  private onAudioData: ((data: Float32Array) => void) | null = null;
  private onError: ((error: string) => void) | null = null;
  
  // State
  private isInitialized = false;
  private isProcessing = false;
  private isAndroid = this.detectAndroid();
  
  constructor() {
    console.log('AudioPipeline: Constructor called', {
      userAgent: navigator.userAgent,
      isAndroid: this.isAndroid
    });
  }

  /**
   * Detect if running on Android
   */
  private detectAndroid(): boolean {
    return /Android/i.test(navigator.userAgent);
  }

  /**
   * Check microphone permission status
   */
  private async checkMicrophonePermission(): Promise<'granted' | 'denied' | 'prompt'> {
    try {
      if (!navigator.permissions?.query) {
        console.log('AudioPipeline: Permissions API not supported, defaulting to "prompt"');
        return 'prompt';
      }

      const result = await navigator.permissions.query({ name: 'microphone' as PermissionName });
      console.log('AudioPipeline: Microphone permission status:', result.state);
      return result.state;
    } catch (error: any) {
      console.warn('AudioPipeline: Permission query failed:', error.message);
      return 'prompt'; // Assume we can try
    }
  }

  /**
   * Try getUserMedia with progressively relaxed constraints
   * Desktop → tries all constraints
   * Android → tries minimal constraints
   */
  private async requestMicrophoneAccess(): Promise<MediaStream | null> {
    // Audio constraints in order of preference (strict to lenient)
    const constraintsList = [
      // Strict: Desktop with all features
      {
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: false,
          sampleRate: { ideal: 16000 }
        } as MediaStreamAudioConstraints
      },
      // Android: Reduce constraints for compatibility
      {
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          sampleRate: { ideal: 16000 }
        } as MediaStreamAudioConstraints
      },
      // Android: Most lenient
      {
        audio: {
          sampleRate: { ideal: 16000 }
        } as MediaStreamAudioConstraints
      },
      // Fallback: Any microphone (some Android devices)
      {
        audio: true
      }
    ];

    // On Android, skip to less strict constraints
    const startIndex = this.isAndroid ? 1 : 0;

    for (let i = startIndex; i < constraintsList.length; i++) {
      try {
        const constraints = constraintsList[i];
        console.log(`AudioPipeline: Attempting getUserMedia with constraint set ${i}:`, constraints);
        
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        console.log(`✓ AudioPipeline: Microphone access granted (constraint ${i})`);
        return stream;
      } catch (error: any) {
        const constraintDesc = i === constraintsList.length - 1 ? 'fallback' : `set ${i}`;
        console.warn(`✗ AudioPipeline: Constraint ${constraintDesc} failed:`, {
          errorName: error.name,
          errorMessage: error.message
        });

        // Stop trying if it's a permission error
        if (error.name === 'NotAllowedError') {
          console.error('AudioPipeline: Permission denied by user or system');
          throw error; // Re-throw to handle in initialize()
        }
      }
    }

    return null; // All constraint attempts failed
  }

  /**
   * Initialize audio context and request microphone access
   */
  async initialize(): Promise<boolean> {
    try {
      console.log('AudioPipeline: Initializing...');

      // Pre-flight: Check permission status
      const permStatus = await this.checkMicrophonePermission();
      if (permStatus === 'denied') {
        const error = 'AudioPipeline: Microphone permission denied. User must reset in Settings.';
        console.error(error);
        if (this.onError) {
          this.onError(error);
        }
        return false;
      }

      // Create audio context (use single instance to avoid quota errors)
      if (!this.audioContext) {
        this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      }

      // Resume audio context if suspended
      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
        console.log('AudioPipeline: Audio context resumed');
      }

      // Request microphone access with fallback constraints
      this.mediaStream = await this.requestMicrophoneAccess();

      if (!this.mediaStream) {
        throw new Error('Failed to obtain microphone stream after all constraint attempts');
      }

      console.log('AudioPipeline: Microphone access granted');

      // Create audio nodes
      this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);
      this.gainNode = this.audioContext.createGain();
      this.analyserNode = this.audioContext.createAnalyser();

      // Create script processor for real-time audio processing
      // Buffer size: 4096 samples (about 256ms at 16kHz)
      const bufferSize = 4096;
      this.scriptProcessor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

      // Connect nodes: source -> gain -> analyser -> scriptProcessor -> destination
      this.sourceNode.connect(this.gainNode);
      this.gainNode.connect(this.analyserNode);
      this.analyserNode.connect(this.scriptProcessor);
      this.scriptProcessor.connect(this.audioContext.destination);

      // Set up audio processing callback
      this.scriptProcessor.onaudioprocess = (event: AudioProcessingEvent) => {
        const inputData = event.inputBuffer.getChannelData(0);
        const audioData = new Float32Array(inputData);

        if (this.isProcessing && this.onAudioData) {
          this.onAudioData(audioData);
        }
      };

      this.isInitialized = true;
      console.log('AudioPipeline: Initialization complete', {
        sampleRate: this.audioContext.sampleRate,
        contextState: this.audioContext.state,
        isAndroid: this.isAndroid
      });
      return true;
    } catch (error: any) {
      const errorDetails = {
        errorName: error.name,
        errorMessage: error.message,
        userAgent: navigator.userAgent,
        isAndroid: this.isAndroid,
        mediaDevicesSupported: !!navigator.mediaDevices,
        getUserMediaSupported: !!navigator.mediaDevices?.getUserMedia
      };

      let friendlyMessage = '';
      switch (error.name) {
        case 'NotAllowedError':
          friendlyMessage = 'Microphone permission denied. Please enable in browser/device settings.';
          break;
        case 'NotFoundError':
          friendlyMessage = 'No microphone device found on this device.';
          break;
        case 'NotReadableError':
          friendlyMessage = 'Microphone is unavailable. Try closing other apps using the mic.';
          break;
        case 'SecurityError':
          friendlyMessage = 'Security error. Ensure you\'re on HTTPS (or localhost).';
          break;
        default:
          friendlyMessage = `Audio initialization failed: ${error.message}`;
      }

      const errorMsg = `AudioPipeline: ${friendlyMessage}`;
      console.error(errorMsg, errorDetails);

      if (this.onError) {
        this.onError(friendlyMessage);
      }
      return false;
    }
  }

  /**
   * Start audio processing
   */
  startProcessing(): void {
    if (!this.isInitialized) {
      const error = 'AudioPipeline: Not initialized. Call initialize() first.';
      console.error(error);
      if (this.onError) {
        this.onError(error);
      }
      return;
    }

    this.isProcessing = true;
    console.log('AudioPipeline: Processing started');
  }

  /**
   * Stop audio processing
   */
  stopProcessing(): void {
    this.isProcessing = false;
    console.log('AudioPipeline: Processing stopped');
  }

  /**
   * Get real-time frequency data (for visualization/VAD)
   */
  getFrequencyData(): Uint8Array | null {
    if (!this.analyserNode) {
      return null;
    }

    const dataArray = new Uint8Array(this.analyserNode.frequencyBinCount);
    this.analyserNode.getByteFrequencyData(dataArray);
    return dataArray;
  }

  /**
   * Get audio level (RMS energy) for silence detection
   */
  getAudioLevel(): number {
    if (!this.analyserNode) {
      return 0;
    }

    const dataArray = new Uint8Array(this.analyserNode.frequencyBinCount);
    this.analyserNode.getByteFrequencyData(dataArray);

    // Calculate RMS (root mean square) energy
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += (dataArray[i] / 255) ** 2;
    }
    const rms = Math.sqrt(sum / dataArray.length);

    return rms;
  }

  /**
   * Set microphone gain (0.0 to 1.0)
   */
  setGain(value: number): void {
    if (this.gainNode) {
      this.gainNode.gain.value = Math.max(0, Math.min(1, value));
      console.log(`AudioPipeline: Gain set to ${this.gainNode.gain.value}`);
    }
  }

  /**
   * Register callback for audio data
   */
  onAudioDataCallback(callback: (data: Float32Array) => void): void {
    this.onAudioData = callback;
  }

  /**
   * Register callback for errors
   */
  onErrorCallback(callback: (error: string) => void): void {
    this.onError = callback;
  }

  /**
   * Cleanup resources
   */
  cleanup(): void {
    try {
      this.isProcessing = false;

      if (this.scriptProcessor) {
        this.scriptProcessor.disconnect();
      }

      if (this.mediaStream) {
        this.mediaStream.getTracks().forEach(track => track.stop());
      }

      // Don't close audio context - might be reused

      console.log('AudioPipeline: Cleanup complete');
    } catch (error) {
      console.error('AudioPipeline: Cleanup error', error);
    }
  }

  /**
   * Get current state
   */
  getState() {
    return {
      isInitialized: this.isInitialized,
      isProcessing: this.isProcessing,
      audioContextState: this.audioContext?.state || 'not-created',
      sampleRate: this.audioContext?.sampleRate || 0,
      isAndroid: this.isAndroid
    };
  }
}
