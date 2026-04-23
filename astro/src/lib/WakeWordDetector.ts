/**
 * Wake Word Detector Module
 * Detects custom wake words using TensorFlow.js
 * Designed for "Hey Archer" and "Go for Archer"
 */

import * as tf from '@tensorflow/tfjs';

export interface WakeWordConfig {
  name: string;
  threshold: number;
  cooldownMs: number; // Prevent rapid re-triggers
}

export interface DetectionResult {
  phrase: string;
  confidence: number;
  timestamp: number;
  detected: boolean;
}

export class WakeWordDetector {
  private model: tf.LayersModel | null = null;
  private isInitialized = false;
  private lastDetectionTime = 0;
  
  private config: {
    heyArcher: WakeWordConfig;
    goForArcher: WakeWordConfig;
  };

  private onDetection: ((result: DetectionResult) => void) | null = null;
  private onError: ((error: string) => void) | null = null;

  constructor() {
    // Configuration for wake word detection
    this.config = {
      heyArcher: {
        name: 'Hey Archer',
        threshold: 0.7, // 70% confidence to trigger
        cooldownMs: 2000 // Wait 2s before detecting again
      },
      goForArcher: {
        name: 'Go for Archer',
        threshold: 0.6, // 60% confidence (more forgiving for close phrase)
        cooldownMs: 1000
      }
    };

    console.log('WakeWordDetector: Constructor called');
  }

  /**
   * Initialize the detector (load model)
   * For now, we'll use a placeholder - real implementation uses custom TFLite model
   */
  async initialize(): Promise<boolean> {
    try {
      console.log('WakeWordDetector: Initializing...');
      
      // TODO: Load actual trained model
      // For MVP, we'll create a simple model for testing
      // Production should use: 
      // this.model = await tf.loadLayersModel('indexeddb://hey-archer-model');
      
      // Create a dummy model for testing (will be replaced with trained model)
      this.model = this.createDummyModel();
      
      this.isInitialized = true;
      console.log('WakeWordDetector: Initialization complete');
      return true;
      
    } catch (error: any) {
      const errorMsg = `WakeWordDetector: Initialization failed - ${error.message}`;
      console.error(errorMsg);
      if (this.onError) {
        this.onError(errorMsg);
      }
      return false;
    }
  }

  /**
   * Create a dummy model for testing (will be replaced with trained model)
   */
  private createDummyModel(): tf.LayersModel {
    // Input: spectrogram (40 mel-bins x 101 frames)
    const input = tf.input({ shape: [40, 101, 1] });
    
    // Conv layer
    const conv1 = tf.layers.conv2d({
      filters: 32,
      kernelSize: [3, 3],
      activation: 'relu'
    }).apply(input) as any;
    
    // Pooling
    const pool1 = tf.layers.maxPooling2d({
      poolSize: [2, 2]
    }).apply(conv1) as any;
    
    // Conv layer 2
    const conv2 = tf.layers.conv2d({
      filters: 64,
      kernelSize: [3, 3],
      activation: 'relu'
    }).apply(pool1) as any;
    
    // Pooling 2
    const pool2 = tf.layers.maxPooling2d({
      poolSize: [2, 2]
    }).apply(conv2) as any;
    
    // Flatten
    const flat = tf.layers.flatten().apply(pool2) as any;
    
    // Dense layers
    const dense1 = tf.layers.dense({
      units: 128,
      activation: 'relu'
    }).apply(flat) as any;
    
    const dropout = tf.layers.dropout({
      rate: 0.5
    }).apply(dense1) as any;
    
    // Output: 2 classes (Hey Archer, Go for Archer)
    const output = tf.layers.dense({
      units: 2,
      activation: 'softmax'
    }).apply(dropout) as any;
    
    const model = tf.model({ inputs: input, outputs: output });
    console.log('WakeWordDetector: Created dummy model for testing');
    
    return model;
  }

  /**
   * Process audio chunk and detect wake words
   * @param audioData Float32Array of audio samples
   */
  async processAudioChunk(audioData: Float32Array): Promise<void> {
    if (!this.isInitialized || !this.model) {
      return;
    }

    try {
      // TODO: Convert audio to spectrogram
      // This is a simplified placeholder
      const spectrogram = await this.audioToSpectrogram(audioData);
      
      // Run inference
      const predictions = this.model.predict(spectrogram) as tf.Tensor;
      const scores = await predictions.data();
      
      // Get predictions for each class
      const heyArcherConfidence = scores[0];
      const goForArcherConfidence = scores[1];
      
      console.log(`WakeWordDetector: Hey Archer=${heyArcherConfidence.toFixed(3)}, Go for Archer=${goForArcherConfidence.toFixed(3)}`);
      
      // Check "Hey Archer"
      if (heyArcherConfidence > this.config.heyArcher.threshold) {
        this.triggerDetection({
          phrase: this.config.heyArcher.name,
          confidence: heyArcherConfidence,
          timestamp: Date.now(),
          detected: true
        });
      }
      
      // Check "Go for Archer"
      if (goForArcherConfidence > this.config.goForArcher.threshold) {
        this.triggerDetection({
          phrase: this.config.goForArcher.name,
          confidence: goForArcherConfidence,
          timestamp: Date.now(),
          detected: true
        });
      }
      
      // Cleanup
      predictions.dispose();
      spectrogram.dispose();
      
    } catch (error: any) {
      console.error('WakeWordDetector: Processing error', error);
    }
  }

  /**
   * Convert raw audio to mel-spectrogram
   * Placeholder implementation - full version uses librosa-equivalent
   */
  private async audioToSpectrogram(audioData: Float32Array): Promise<tf.Tensor> {
    // TODO: Implement proper FFT + mel-scale conversion
    // For now, return a dummy tensor matching expected shape
    const dummy = tf.zeros([1, 40, 101, 1]);
    return dummy;
  }

  /**
   * Trigger detection callback with cooldown
   */
  private triggerDetection(result: DetectionResult): void {
    const now = Date.now();
    const timeSinceLastDetection = now - this.lastDetectionTime;
    
    const cooldown = result.phrase === this.config.heyArcher.name 
      ? this.config.heyArcher.cooldownMs 
      : this.config.goForArcher.cooldownMs;
    
    if (timeSinceLastDetection > cooldown) {
      this.lastDetectionTime = now;
      console.log(`✓ Wake word detected: "${result.phrase}" (confidence: ${result.confidence.toFixed(3)})`);
      
      if (this.onDetection) {
        this.onDetection(result);
      }
    }
  }

  /**
   * Register detection callback
   */
  onDetectionCallback(callback: (result: DetectionResult) => void): void {
    this.onDetection = callback;
  }

  /**
   * Register error callback
   */
  onErrorCallback(callback: (error: string) => void): void {
    this.onError = callback;
  }

  /**
   * Update detection threshold
   */
  setThreshold(phrase: 'heyArcher' | 'goForArcher', threshold: number): void {
    const key = phrase === 'heyArcher' ? 'heyArcher' : 'goForArcher';
    this.config[key].threshold = Math.max(0, Math.min(1, threshold));
    console.log(`WakeWordDetector: Threshold for "${this.config[key].name}" set to ${this.config[key].threshold}`);
  }

  /**
   * Cleanup resources
   */
  cleanup(): void {
    try {
      if (this.model) {
        this.model.dispose();
      }
      console.log('WakeWordDetector: Cleanup complete');
    } catch (error) {
      console.error('WakeWordDetector: Cleanup error', error);
    }
  }

  /**
   * Get current state
   */
  getState() {
    return {
      isInitialized: this.isInitialized,
      modelLoaded: this.model !== null,
      thresholds: {
        heyArcher: this.config.heyArcher.threshold,
        goForArcher: this.config.goForArcher.threshold
      }
    };
  }
}
