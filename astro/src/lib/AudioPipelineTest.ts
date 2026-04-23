/**
 * Audio Pipeline Integration Test
 * Tests: AudioPipeline + WakeWordDetector + SilenceDetector
 */

import { AudioPipeline } from './AudioPipeline';
import { WakeWordDetector } from './WakeWordDetector';
import { SilenceDetector } from './SilenceDetector';

export class AudioPipelineTest {
  private audioPipeline: AudioPipeline;
  private wakeWordDetector: WakeWordDetector;
  private silenceDetector: SilenceDetector;
  
  private isRunning = false;
  private processingInterval: number | null = null;

  constructor() {
    this.audioPipeline = new AudioPipeline();
    this.wakeWordDetector = new WakeWordDetector();
    this.silenceDetector = new SilenceDetector();

    console.log('AudioPipelineTest: Constructor called');
  }

  /**
   * Initialize all components
   */
  async initialize(): Promise<boolean> {
    try {
      console.log('AudioPipelineTest: Starting initialization...\n');

      // Initialize audio pipeline
      console.log('[1/3] Initializing AudioPipeline...');
      const audioPipelineOk = await this.audioPipeline.initialize();
      if (!audioPipelineOk) {
        console.error('❌ AudioPipeline initialization failed');
        return false;
      }
      console.log('✓ AudioPipeline initialized\n');

      // Initialize wake word detector
      console.log('[2/3] Initializing WakeWordDetector...');
      const detectorOk = await this.wakeWordDetector.initialize();
      if (!detectorOk) {
        console.error('❌ WakeWordDetector initialization failed');
        return false;
      }
      console.log('✓ WakeWordDetector initialized\n');

      // Register callbacks
      console.log('[3/3] Setting up callbacks...');
      
      this.wakeWordDetector.onDetectionCallback((result) => {
        console.log(`🎤 WAKE WORD DETECTED: "${result.phrase}" (${(result.confidence * 100).toFixed(1)}%)`);
      });

      this.silenceDetector.onSilenceCallback((duration) => {
        console.log(`🔇 SILENCE DETECTED: ${duration}ms`);
      });

      this.silenceDetector.onAudioCallback(() => {
        console.log('🔊 Audio detected');
      });

      console.log('✓ Callbacks registered\n');

      console.log('===========================================');
      console.log('✅ ALL COMPONENTS INITIALIZED SUCCESSFULLY');
      console.log('===========================================\n');

      return true;

    } catch (error) {
      console.error('❌ Initialization failed:', error);
      return false;
    }
  }

  /**
   * Start the processing loop
   */
  start(): void {
    if (this.isRunning) {
      console.warn('AudioPipelineTest: Already running');
      return;
    }

    console.log('🟢 Starting audio processing...\n');
    this.isRunning = true;

    this.audioPipeline.startProcessing();

    // Set up audio processing callback
    this.audioPipeline.onAudioDataCallback((audioData: Float32Array) => {
      // Process audio through wake word detector
      this.wakeWordDetector.processAudioChunk(audioData);
    });

    // Set up frequency monitoring for silence detection
    this.processingInterval = window.setInterval(() => {
      const frequencyData = this.audioPipeline.getFrequencyData();
      if (frequencyData) {
        this.silenceDetector.processFrequencyData(frequencyData);
      }
    }, 100) as any; // Check every 100ms

    console.log('Audio processing started. Listening...\n');
  }

  /**
   * Stop the processing loop
   */
  stop(): void {
    if (!this.isRunning) {
      console.warn('AudioPipelineTest: Not running');
      return;
    }

    console.log('\n🔴 Stopping audio processing...');
    this.isRunning = false;

    if (this.processingInterval) {
      clearInterval(this.processingInterval);
    }

    this.audioPipeline.stopProcessing();
    console.log('Audio processing stopped\n');
  }

  /**
   * Print state of all components
   */
  printState(): void {
    console.log('\n=== Component States ===\n');
    console.log('AudioPipeline:', this.audioPipeline.getState());
    console.log('WakeWordDetector:', this.wakeWordDetector.getState());
    console.log('SilenceDetector:', this.silenceDetector.getState());
  }

  /**
   * Cleanup
   */
  cleanup(): void {
    console.log('Cleaning up...');
    this.stop();
    this.audioPipeline.cleanup();
    this.wakeWordDetector.cleanup();
  }
}

/**
 * Export test runner for use in browser console
 */
export async function runAudioPipelineTest() {
  console.clear();
  console.log('╔════════════════════════════════════════════╗');
  console.log('║  Audio Pipeline Integration Test           ║');
  console.log('║  Phase 1.1: Audio Pipeline + Wake Words   ║');
  console.log('╚════════════════════════════════════════════╝\n');

  const test = new AudioPipelineTest();

  const initialized = await test.initialize();
  if (!initialized) {
    console.error('Failed to initialize test');
    return;
  }

  test.start();

  // Auto-stop after 60 seconds for testing
  const autoStopTimeout = setTimeout(() => {
    console.log('\n⏱️ Auto-stop triggered (60s timeout)');
    test.stop();
    test.printState();
    test.cleanup();
  }, 60000);

  // Export to window for manual control
  (window as any).audioTest = {
    test,
    stop: () => {
      clearTimeout(autoStopTimeout);
      test.stop();
      test.printState();
      test.cleanup();
    },
    printState: () => test.printState(),
    start: () => test.start()
  };

  console.log('💡 TIP: Use window.audioTest to control the test');
  console.log('   - window.audioTest.stop() - Stop processing');
  console.log('   - window.audioTest.printState() - Print component states');
  console.log('   - window.audioTest.start() - Resume processing\n');
}
