/**
 * Silence Detector (Voice Activity Detection)
 * Detects when user stops speaking using energy-based threshold
 */

export interface VADConfig {
  energyThreshold: number; // 0.0 to 1.0
  silenceDurationMs: number; // Milliseconds of silence before triggering
  frequencyBandwidth: number; // Frequency band to monitor (Hz)
}

export class SilenceDetector {
  private config: VADConfig;
  private silenceStartTime: number | null = null;
  private lastAudioTime: number = Date.now();
  
  private onSilenceDetected: ((durationMs: number) => void) | null = null;
  private onAudioDetected: (() => void) | null = null;

  constructor(config?: Partial<VADConfig>) {
    this.config = {
      energyThreshold: 0.02, // 2% energy threshold
      silenceDurationMs: 2500, // 2.5 seconds of silence
      frequencyBandwidth: 4000, // Focus on 0-4kHz (speech range)
      ...config
    };

    console.log('SilenceDetector: Initialized with config', this.config);
  }

  /**
   * Process audio data and detect silence
   * @param frequencyData Uint8Array from analyser.getByteFrequencyData()
   */
  processFrequencyData(frequencyData: Uint8Array): void {
    const energy = this.calculateEnergy(frequencyData);
    const isAudio = energy > this.config.energyThreshold;

    if (isAudio) {
      // Audio detected - reset silence timer
      if (this.silenceStartTime !== null) {
        console.log(`SilenceDetector: Audio resumed after ${Date.now() - this.silenceStartTime}ms`);
        this.silenceStartTime = null;
      }

      this.lastAudioTime = Date.now();

      if (this.onAudioDetected) {
        this.onAudioDetected();
      }
    } else {
      // No audio - start or update silence timer
      if (this.silenceStartTime === null) {
        this.silenceStartTime = Date.now();
        console.log('SilenceDetector: Silence started');
      } else {
        const silenceDuration = Date.now() - this.silenceStartTime;

        // Check if silence threshold reached
        if (silenceDuration >= this.config.silenceDurationMs) {
          this.triggerSilenceDetection(silenceDuration);
          this.silenceStartTime = null; // Reset after detection
        }
      }
    }
  }

  /**
   * Calculate energy (RMS) from frequency data
   */
  private calculateEnergy(frequencyData: Uint8Array): number {
    let sum = 0;
    
    // Use only lower frequencies (speech is typically 80-8000 Hz)
    // With typical 4kHz FFT bin size, focus on first ~40 bins
    const binCount = Math.min(40, frequencyData.length);
    
    for (let i = 0; i < binCount; i++) {
      const normalized = frequencyData[i] / 255;
      sum += normalized * normalized;
    }

    const rms = Math.sqrt(sum / binCount);
    return rms; // 0.0 to 1.0
  }

  /**
   * Trigger silence detection
   */
  private triggerSilenceDetection(durationMs: number): void {
    console.log(`✓ Silence detected (${durationMs}ms)`);

    if (this.onSilenceDetected) {
      this.onSilenceDetected(durationMs);
    }
  }

  /**
   * Reset silence timer manually
   */
  reset(): void {
    this.silenceStartTime = null;
    console.log('SilenceDetector: Reset');
  }

  /**
   * Register callback for silence detection
   */
  onSilenceCallback(callback: (durationMs: number) => void): void {
    this.onSilenceDetected = callback;
  }

  /**
   * Register callback for audio detection
   */
  onAudioCallback(callback: () => void): void {
    this.onAudioDetected = callback;
  }

  /**
   * Update energy threshold
   */
  setEnergyThreshold(value: number): void {
    this.config.energyThreshold = Math.max(0, Math.min(1, value));
    console.log(`SilenceDetector: Energy threshold set to ${this.config.energyThreshold}`);
  }

  /**
   * Update silence duration
   */
  setSilenceDuration(ms: number): void {
    this.config.silenceDurationMs = Math.max(100, ms);
    console.log(`SilenceDetector: Silence duration set to ${this.config.silenceDurationMs}ms`);
  }

  /**
   * Get current state
   */
  getState() {
    return {
      isSilent: this.silenceStartTime !== null,
      silenceStartTime: this.silenceStartTime,
      lastAudioTime: this.lastAudioTime,
      config: this.config
    };
  }
}
