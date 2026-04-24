/**
 * DiagnosticLogger.ts
 * 
 * Comprehensive logging system that works even when browser console is unavailable.
 * Captures initialization lifecycle events and sends telemetry to server.
 * 
 * Problem: Phone browser has no console access. Voice interface hangs on "Checking..."
 * Solution: Log to sessionStorage + send periodic telemetry to backend
 * 
 * Usage:
 *   const logger = DiagnosticLogger.getInstance()
 *   logger.log('INIT_START', { component: 'VoiceStateMachine' })
 *   logger.captureError('AUDIO_CONTEXT_FAILED', error)
 */

type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'CRITICAL';

interface LogEntry {
  timestamp: number;
  level: LogLevel;
  category: string;
  message: string;
  data?: Record<string, any>;
  stack?: string;
}

interface DiagnosticState {
  initStartTime: number;
  logs: LogEntry[];
  errors: LogEntry[];
  telemetrySent: boolean;
  lastTelemetryTime: number;
  currentPhase: string;
}

export class DiagnosticLogger {
  private static instance: DiagnosticLogger;
  private state: DiagnosticState;
  private readonly MAX_LOGS = 500;
  private readonly TELEMETRY_INTERVAL = 3000; // Send every 3 seconds if errors
  private readonly SESSION_STORAGE_KEY = 'voice_diagnostics';
  private telemetryTimer: NodeJS.Timeout | null = null;
  private telemetryEndpoint: string;

  private constructor(telemetryEndpoint = '/api/voice/diagnostics') {
    this.telemetryEndpoint = telemetryEndpoint;
    this.state = this.loadState();
    this.startAutoTelemetry();
  }

  static getInstance(endpoint?: string): DiagnosticLogger {
    if (!DiagnosticLogger.instance) {
      DiagnosticLogger.instance = new DiagnosticLogger(endpoint);
    }
    return DiagnosticLogger.instance;
  }

  private loadState(): DiagnosticState {
    try {
      const stored = sessionStorage.getItem(this.SESSION_STORAGE_KEY);
      if (stored) {
        return JSON.parse(stored);
      }
    } catch (e) {
      console.warn('Failed to load diagnostic state from storage');
    }
    return {
      initStartTime: Date.now(),
      logs: [],
      errors: [],
      telemetrySent: false,
      lastTelemetryTime: 0,
      currentPhase: 'INIT',
    };
  }

  private persistState(): void {
    try {
      sessionStorage.setItem(this.SESSION_STORAGE_KEY, JSON.stringify(this.state));
    } catch (e) {
      console.warn('Failed to persist diagnostic state');
    }
  }

  /**
   * Log a lifecycle event
   */
  log(category: string, data?: Record<string, any>, level: LogLevel = 'INFO'): void {
    const entry: LogEntry = {
      timestamp: Date.now(),
      level,
      category,
      message: category,
      data,
    };

    this.state.logs.push(entry);
    if (this.state.logs.length > this.MAX_LOGS) {
      this.state.logs.shift();
    }

    // Console if available
    if (typeof console !== 'undefined') {
      console[level === 'CRITICAL' || level === 'ERROR' ? 'error' : 'log'](
        `[VOICE:${category}]`,
        data
      );
    }

    this.persistState();
  }

  /**
   * Capture an error with stack trace
   */
  captureError(category: string, error: Error, context?: Record<string, any>): void {
    const entry: LogEntry = {
      timestamp: Date.now(),
      level: 'ERROR',
      category,
      message: error.message,
      data: context,
      stack: error.stack,
    };

    this.state.errors.push(entry);
    if (this.state.errors.length > 100) {
      this.state.errors.shift();
    }

    console?.error(`[VOICE:${category}]`, error, context);
    this.persistState();

    // Trigger immediate telemetry if we have critical errors
    if (category.includes('INITIALIZATION') || category.includes('FATAL')) {
      this.sendTelemetryNow();
    }
  }

  /**
   * Update current initialization phase
   */
  setPhase(phase: string): void {
    this.state.currentPhase = phase;
    this.log('PHASE_CHANGE', { phase }, 'DEBUG');
    this.persistState();
  }

  /**
   * Check if we're stuck (no progress in X seconds)
   */
  isStuck(timeoutMs = 5000): boolean {
    if (this.state.logs.length === 0) return false;
    const lastLog = this.state.logs[this.state.logs.length - 1];
    const elapsed = Date.now() - lastLog.timestamp;
    return elapsed > timeoutMs;
  }

  /**
   * Get human-readable diagnostic summary
   */
  getSummary(): string {
    const runtime = Date.now() - this.state.initStartTime;
    const hasErrors = this.state.errors.length > 0;
    const lastError = this.state.errors[this.state.errors.length - 1];
    const isStuck = this.isStuck();

    let summary = `VOICE DIAGNOSTIC REPORT\n`;
    summary += `Runtime: ${runtime}ms\n`;
    summary += `Current Phase: ${this.state.currentPhase}\n`;
    summary += `Total Logs: ${this.state.logs.length}\n`;
    summary += `Total Errors: ${this.state.errors.length}\n`;
    summary += `Status: ${isStuck ? '🔴 STUCK' : '🟢 PROGRESSING'}\n`;

    if (hasErrors) {
      summary += `\nLast Error: ${lastError.category}\n`;
      summary += `Message: ${lastError.message}\n`;
    }

    summary += `\nLast 10 Events:\n`;
    const recentLogs = this.state.logs.slice(-10);
    for (const log of recentLogs) {
      const elapsed = log.timestamp - this.state.initStartTime;
      summary += `  [${elapsed}ms] ${log.category}\n`;
    }

    return summary;
  }

  /**
   * Send telemetry to backend
   */
  private async sendTelemetryNow(): Promise<void> {
    const now = Date.now();
    if (now - this.state.lastTelemetryTime < 1000) {
      return; // Rate limit
    }

    try {
      const payload = {
        timestamp: now,
        runtime: now - this.state.initStartTime,
        phase: this.state.currentPhase,
        logsCount: this.state.logs.length,
        errorsCount: this.state.errors.length,
        lastError: this.state.errors[this.state.errors.length - 1] || null,
        isStuck: this.isStuck(),
        userAgent: navigator.userAgent,
        logs: this.state.logs.slice(-50), // Last 50 logs
      };

      await fetch(this.telemetryEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true,
      });

      this.state.lastTelemetryTime = now;
      this.state.telemetrySent = true;
      this.persistState();
    } catch (e) {
      console?.warn('Failed to send telemetry', e);
    }
  }

  /**
   * Auto-send telemetry every N seconds if there are errors
   */
  private startAutoTelemetry(): void {
    if (this.telemetryTimer) clearInterval(this.telemetryTimer);

    this.telemetryTimer = setInterval(() => {
      if (this.state.errors.length > 0 || this.isStuck()) {
        this.sendTelemetryNow();
      }
    }, this.TELEMETRY_INTERVAL) as unknown as NodeJS.Timeout;

    // Send telemetry on page unload
    if (typeof window !== 'undefined') {
      window.addEventListener('unload', () => this.sendTelemetryNow());
      window.addEventListener('beforeunload', () => this.sendTelemetryNow());
    }
  }

  /**
   * Get all logs for debugging
   */
  getLogs(): LogEntry[] {
    return this.state.logs;
  }

  /**
   * Get all errors
   */
  getErrors(): LogEntry[] {
    return this.state.errors;
  }

  /**
   * Clear diagnostics
   */
  clear(): void {
    this.state = {
      initStartTime: Date.now(),
      logs: [],
      errors: [],
      telemetrySent: false,
      lastTelemetryTime: 0,
      currentPhase: 'INIT',
    };
    this.persistState();
  }

  /**
   * Inject diagnostic UI overlay for showing errors without console
   */
  injectDiagnosticUI(): HTMLDivElement {
    const overlay = document.createElement('div');
    overlay.id = 'voice-diagnostic-overlay';
    overlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.8);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 99999;
      font-family: monospace;
      color: #fff;
      padding: 20px;
    `;

    const panel = document.createElement('div');
    panel.style.cssText = `
      background: #1e1e1e;
      border: 2px solid #ff6b6b;
      border-radius: 8px;
      padding: 20px;
      max-width: 90%;
      max-height: 80vh;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-all;
      line-height: 1.4;
    `;

    panel.textContent = this.getSummary();
    overlay.appendChild(panel);

    document.body.appendChild(overlay);
    return overlay;
  }
}

export default DiagnosticLogger;
