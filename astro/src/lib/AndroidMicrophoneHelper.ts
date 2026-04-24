/**
 * Android Microphone Helper Utility
 * Provides Android-specific utilities for microphone permission handling
 * and diagnostic information
 */

export interface MicrophoneDiagnostics {
  isAndroid: boolean;
  permissionStatus: 'granted' | 'denied' | 'prompt' | 'unknown';
  mediaDevicesSupported: boolean;
  getUserMediaSupported: boolean;
  audioContextSupported: boolean;
  speechRecognitionSupported: boolean;
  userAgent: string;
  browser: string;
  errorMessage?: string;
}

export class AndroidMicrophoneHelper {
  /**
   * Detect if running on Android
   */
  static isAndroid(): boolean {
    return /Android/i.test(navigator.userAgent);
  }

  /**
   * Detect browser type on Android
   */
  static getBrowserType(): string {
    const ua = navigator.userAgent;
    if (/Chrome/.test(ua)) return 'Chrome';
    if (/Firefox/.test(ua)) return 'Firefox';
    if (/Samsung/.test(ua)) return 'Samsung Internet';
    if (/Edge/.test(ua)) return 'Edge';
    if (/OPR/.test(ua)) return 'Opera';
    return 'Unknown';
  }

  /**
   * Get comprehensive microphone diagnostics
   */
  static async getDiagnostics(): Promise<MicrophoneDiagnostics> {
    const isAndroid = this.isAndroid();
    let permissionStatus: 'granted' | 'denied' | 'prompt' | 'unknown' = 'unknown';

    try {
      if (navigator.permissions?.query) {
        const result = await navigator.permissions.query({ name: 'microphone' as PermissionName });
        permissionStatus = result.state;
      }
    } catch (error) {
      console.warn('Failed to query permission:', error);
    }

    return {
      isAndroid,
      permissionStatus,
      mediaDevicesSupported: !!navigator.mediaDevices,
      getUserMediaSupported: !!navigator.mediaDevices?.getUserMedia,
      audioContextSupported: !!(window.AudioContext || (window as any).webkitAudioContext),
      speechRecognitionSupported: !!(window.SpeechRecognition || (window as any).webkitSpeechRecognition),
      userAgent: navigator.userAgent,
      browser: this.getBrowserType()
    };
  }

  /**
   * Get user-friendly diagnostic message
   */
  static async getDiagnosticMessage(): Promise<string> {
    const diag = await this.getDiagnostics();
    const lines = [
      `🔍 Microphone Diagnostics`,
      `━━━━━━━━━━━━━━━━━━━━━━━`,
      `Platform: ${diag.isAndroid ? '📱 Android' : '🖥️ Desktop'}`,
      `Browser: ${diag.browser}`,
      `Permission: ${this.permissionStatusToEmoji(diag.permissionStatus)} ${diag.permissionStatus}`,
      ``,
      `API Support:`,
      `  mediaDevices: ${diag.mediaDevicesSupported ? '✓' : '✗'}`,
      `  getUserMedia: ${diag.getUserMediaSupported ? '✓' : '✗'}`,
      `  AudioContext: ${diag.audioContextSupported ? '✓' : '✗'}`,
      `  SpeechRecognition: ${diag.speechRecognitionSupported ? '✓' : '✗'}`
    ];

    if (diag.permissionStatus === 'denied') {
      lines.push(``, `⚠️ Next Steps:`, `1. Open Settings > Apps > [Browser]`, `2. Permissions > Microphone > Allow`);
    }

    return lines.join('\n');
  }

  /**
   * Helper: Convert permission status to emoji
   */
  private static permissionStatusToEmoji(status: string): string {
    switch (status) {
      case 'granted':
        return '✅';
      case 'denied':
        return '❌';
      case 'prompt':
        return '⚠️';
      default:
        return '❓';
    }
  }

  /**
   * Generate HTML for diagnostic display
   */
  static async getDiagnosticHTML(): Promise<string> {
    const diag = await this.getDiagnostics();
    return `
      <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; font-family: monospace; font-size: 12px;">
        <h3 style="margin-top: 0;">🔍 Microphone Diagnostics</h3>
        <table style="width: 100%; border-collapse: collapse;">
          <tr style="background: #e0e0e0;">
            <td style="padding: 8px; border: 1px solid #ccc;"><strong>Property</strong></td>
            <td style="padding: 8px; border: 1px solid #ccc;"><strong>Value</strong></td>
          </tr>
          <tr>
            <td style="padding: 8px; border: 1px solid #ccc;">Platform</td>
            <td style="padding: 8px; border: 1px solid #ccc;">${diag.isAndroid ? '📱 Android' : '🖥️ Desktop'}</td>
          </tr>
          <tr>
            <td style="padding: 8px; border: 1px solid #ccc;">Browser</td>
            <td style="padding: 8px; border: 1px solid #ccc;">${diag.browser}</td>
          </tr>
          <tr>
            <td style="padding: 8px; border: 1px solid #ccc;">Permission Status</td>
            <td style="padding: 8px; border: 1px solid #ccc;">${this.permissionStatusToEmoji(diag.permissionStatus)} ${diag.permissionStatus}</td>
          </tr>
          <tr>
            <td style="padding: 8px; border: 1px solid #ccc;">mediaDevices API</td>
            <td style="padding: 8px; border: 1px solid #ccc;">${diag.mediaDevicesSupported ? '✓ Supported' : '✗ Not Supported'}</td>
          </tr>
          <tr>
            <td style="padding: 8px; border: 1px solid #ccc;">getUserMedia()</td>
            <td style="padding: 8px; border: 1px solid #ccc;">${diag.getUserMediaSupported ? '✓ Supported' : '✗ Not Supported'}</td>
          </tr>
          <tr>
            <td style="padding: 8px; border: 1px solid #ccc;">AudioContext</td>
            <td style="padding: 8px; border: 1px solid #ccc;">${diag.audioContextSupported ? '✓ Supported' : '✗ Not Supported'}</td>
          </tr>
          <tr>
            <td style="padding: 8px; border: 1px solid #ccc;">SpeechRecognition</td>
            <td style="padding: 8px; border: 1px solid #ccc;">${diag.speechRecognitionSupported ? '✓ Supported' : '✗ Not Supported'}</td>
          </tr>
        </table>
        ${
          diag.permissionStatus === 'denied'
            ? `
        <div style="margin-top: 15px; padding: 10px; background: #fff3cd; border-left: 4px solid #ffc107; border-radius: 4px;">
          <strong>⚠️ Permission Issue Detected</strong>
          <p>Microphone permission was previously denied.</p>
          <p><strong>To fix:</strong></p>
          <ol>
            <li>Open Settings</li>
            <li>Go to Apps > ${diag.browser}</li>
            <li>Select Permissions > Microphone</li>
            <li>Choose "Allow"</li>
            <li>Refresh this page</li>
          </ol>
        </div>
            `
            : ''
        }
      </div>
    `;
  }

  /**
   * Request microphone with user-friendly error handling
   */
  static async requestMicrophoneWithFallback(): Promise<MediaStream | null> {
    const constraints = [
      // Full featured (Desktop/modern Android)
      {
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: false,
          sampleRate: { ideal: 16000 }
        }
      },
      // Reduced features (older Android)
      {
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          sampleRate: { ideal: 16000 }
        }
      },
      // Minimal (Android fallback)
      {
        audio: {
          sampleRate: { ideal: 16000 }
        }
      },
      // Any microphone
      { audio: true }
    ];

    for (const constraint of constraints) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia(constraint as MediaStreamConstraints);
        console.log('✓ Microphone request successful with constraint:', constraint);
        return stream;
      } catch (error: any) {
        if (error.name === 'NotAllowedError') {
          throw error; // Permission error, don't retry
        }
        // Try next constraint
      }
    }

    return null;
  }

  /**
   * Format detailed error for display
   */
  static formatErrorForDisplay(error: any): string {
    let message = 'Microphone Error';
    let details = '';

    switch (error.name) {
      case 'NotAllowedError':
        message = '❌ Permission Denied';
        details =
          'Microphone permission was denied. Please grant microphone access in your browser and device settings.';
        break;
      case 'NotFoundError':
        message = '❌ No Microphone Found';
        details = 'No microphone device was detected on this device. Check your device settings.';
        break;
      case 'NotReadableError':
        message = '❌ Microphone In Use';
        details = 'Your microphone is currently unavailable or in use by another application.';
        break;
      case 'SecurityError':
        message = '❌ Security Error';
        details = 'Microphone access requires a secure context (HTTPS). Check your connection.';
        break;
      case 'OverconstrainedError':
        message = '❌ Device Doesn\'t Support Requirements';
        details =
          'Your device cannot meet the audio requirements. Try refreshing the page.';
        break;
      default:
        message = '❌ Initialization Failed';
        details = `Error: ${error.message}`;
    }

    return `<h3>${message}</h3><p>${details}</p>`;
  }
}
