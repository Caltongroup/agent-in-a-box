"""
voice_diagnostics_backend.py

Flask endpoint to receive browser-side voice interface diagnostics.
Logs all initialization failures and hangs for server-side analysis.

Installation: Add to your Flask app
    from voice_diagnostics_backend import register_voice_diagnostics
    register_voice_diagnostics(app)
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
import json
import logging

# Create logger for voice diagnostics
logger = logging.getLogger(__name__)

# Store diagnostic reports (in production, use database)
DIAGNOSTIC_REPORTS = []
MAX_REPORTS = 1000

voice_diagnostics_bp = Blueprint('voice_diagnostics', __name__, url_prefix='/api/voice')

@voice_diagnostics_bp.route('/diagnostics', methods=['POST'])
def receive_diagnostics():
    """
    Receive diagnostic telemetry from browser voice interface.
    
    Expected payload:
    {
        "timestamp": 1713980300000,
        "runtime": 12450,
        "phase": "CHECKING_MICROPHONE",
        "logsCount": 15,
        "errorsCount": 1,
        "lastError": { "category": "MICROPHONE_CHECK_FAILED", "message": "..." },
        "isStuck": true,
        "userAgent": "Mozilla/5.0...",
        "logs": [...]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON payload"}), 400
        
        # Add server-side metadata
        report = {
            "received_at": datetime.utcnow().isoformat(),
            "server_time": datetime.utcnow().timestamp(),
            "ip_address": request.remote_addr,
            "user_agent": data.get("userAgent", "unknown"),
            **data  # Include all client data
        }
        
        # Store report
        DIAGNOSTIC_REPORTS.append(report)
        if len(DIAGNOSTIC_REPORTS) > MAX_REPORTS:
            DIAGNOSTIC_REPORTS.pop(0)
        
        # Log if error or stuck
        if data.get("isStuck") or data.get("errorsCount", 0) > 0:
            logger.warning(
                f"Voice initialization issue detected: "
                f"phase={data.get('phase')}, "
                f"runtime={data.get('runtime')}ms, "
                f"errors={data.get('errorsCount')}, "
                f"stuck={data.get('isStuck')}",
                extra={"report": report}
            )
        
        logger.debug(f"Voice diagnostics received: runtime={data.get('runtime')}ms, phase={data.get('phase')}")
        
        return jsonify({
            "status": "ok",
            "message": "Diagnostics received",
            "server_time": report["server_time"]
        }), 200
    
    except Exception as e:
        logger.error(f"Failed to process voice diagnostics: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@voice_diagnostics_bp.route('/health', methods=['GET'])
def voice_health():
    """
    Health check endpoint for voice interface initialization.
    Should return 200 immediately if backend is operational.
    """
    try:
        return jsonify({
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat(),
            "voice_service": "operational"
        }), 200
    except Exception as e:
        logger.error(f"Voice health check failed: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@voice_diagnostics_bp.route('/reports', methods=['GET'])
def get_reports():
    """
    Get recent diagnostic reports (for debugging).
    Filter by:
    - ?stuck=true - only stuck initialization attempts
    - ?errors=true - only reports with errors
    - ?limit=10 - limit number of reports
    """
    try:
        # Apply filters
        reports = DIAGNOSTIC_REPORTS.copy()
        
        if request.args.get('stuck') == 'true':
            reports = [r for r in reports if r.get('isStuck')]
        
        if request.args.get('errors') == 'true':
            reports = [r for r in reports if r.get('errorsCount', 0) > 0]
        
        # Limit
        limit = int(request.args.get('limit', 50))
        reports = reports[-limit:]
        
        return jsonify({
            "total": len(DIAGNOSTIC_REPORTS),
            "returned": len(reports),
            "reports": reports
        }), 200
    
    except Exception as e:
        logger.error(f"Failed to get diagnostic reports: {e}")
        return jsonify({"error": str(e)}), 500

@voice_diagnostics_bp.route('/reports/summary', methods=['GET'])
def get_reports_summary():
    """
    Get summary statistics of diagnostic reports.
    """
    try:
        total = len(DIAGNOSTIC_REPORTS)
        stuck = sum(1 for r in DIAGNOSTIC_REPORTS if r.get('isStuck'))
        with_errors = sum(1 for r in DIAGNOSTIC_REPORTS if r.get('errorsCount', 0) > 0)
        avg_runtime = sum(r.get('runtime', 0) for r in DIAGNOSTIC_REPORTS) / total if total > 0 else 0
        
        # Get most common errors
        error_counts = {}
        for report in DIAGNOSTIC_REPORTS:
            last_error = report.get('lastError')
            if last_error:
                category = last_error.get('category', 'UNKNOWN')
                error_counts[category] = error_counts.get(category, 0) + 1
        
        most_common_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return jsonify({
            "total_reports": total,
            "stuck_count": stuck,
            "with_errors_count": with_errors,
            "avg_runtime_ms": round(avg_runtime),
            "success_rate": round((total - with_errors) / total * 100, 1) if total > 0 else 0,
            "most_common_errors": [
                {"error": err, "count": count} for err, count in most_common_errors
            ]
        }), 200
    
    except Exception as e:
        logger.error(f"Failed to get summary: {e}")
        return jsonify({"error": str(e)}), 500

@voice_diagnostics_bp.route('/reports/clear', methods=['DELETE'])
def clear_reports():
    """
    Clear all diagnostic reports (admin only).
    """
    global DIAGNOSTIC_REPORTS
    try:
        count = len(DIAGNOSTIC_REPORTS)
        DIAGNOSTIC_REPORTS = []
        logger.info(f"Cleared {count} diagnostic reports")
        return jsonify({
            "status": "ok",
            "cleared": count
        }), 200
    except Exception as e:
        logger.error(f"Failed to clear reports: {e}")
        return jsonify({"error": str(e)}), 500

def register_voice_diagnostics(app, blueprintname='voice_diagnostics'):
    """
    Register the voice diagnostics blueprint with your Flask app.
    
    Usage:
        from voice_diagnostics_backend import register_voice_diagnostics
        register_voice_diagnostics(app)
    """
    app.register_blueprint(voice_diagnostics_bp, name=blueprintname)
    logger.info("Voice diagnostics endpoints registered")

# Quick reference for monitoring
def get_critical_issues():
    """
    Get a list of critical issues from recent reports.
    Useful for alerting.
    """
    critical = []
    for report in DIAGNOSTIC_REPORTS[-100:]:  # Last 100 reports
        if report.get('isStuck') or report.get('errorsCount', 0) > 0:
            critical.append({
                "timestamp": report.get('received_at'),
                "phase": report.get('phase'),
                "error": report.get('lastError'),
                "stuck": report.get('isStuck')
            })
    return critical
