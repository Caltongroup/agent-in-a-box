/**
 * Audio Pipeline Module
 * Handles continuous audio streaming, noise suppression, and real-time processing
 * Uses Web Audio API for low-latency audio capture and processing
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
  
  constructor() {
    console.log('AudioPipeline: Constructor called');
  }

  /**
   * Initialize audio context and request microphone access
   */
  async initialize(): Promise<boolean> {
    try {
      console.log('AudioPipeline: Initializing...');
      
      // Create audio context (use single instance to avoid quota errors)
      if (!this.audioContext) {
        this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      }
      
      // Resume audio context if suspended
      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
        console.log('AudioPipeline: Audio context resumed');
      }
      
      // Request microphone access
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: false, // We control gain manually
          sampleRate: { ideal: 16000 } // Ideal for speech recognition
        }
      });
      
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
      console.log('AudioPipeline: Initialization complete');
      return true;
      
    } catch (error: any) {
      const errorMsg = `AudioPipeline: Initialization failed - ${error.message}`;
      console.error(errorMsg);
      if (this.onError) {
        this.onError(errorMsg);
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
      sampleRate: this.audioContext?.sampleRate || 0
    };
  }
}
