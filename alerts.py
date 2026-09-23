"""
Rule engine: evaluates the latest metric row per server against thresholds
and raises alerts. High-severity alerts trigger a simulated automated
remediation action (what a real system would do via a runbook/webhook —
e.g. restart a service or scale out) and the outcome is logged back onto
the alert row. This is the "automation" half of the dashboard.
"""
from datetime import datetime, timezone

from database import get_conn

THRESHOLDS = {
    "cpu_percent": {"warning": 75.0, "critical": 90.0},
    "memory_percent": {"warning": 80.0, "critical": 92.0},
    "disk_percent": {"warning": 85.0, "critical": 95.0},
}

REMEDIATION_BY_METRIC = {
    "cpu_percent": "restart_high_cpu_process",
    "memory_percent": "clear_cache_and_restart_service",
    "disk_percent": "rotate_and_compress_old_logs",
}


def _severity(metric: str, value: float):
    t = THRESHOLDS[metric]
    if value >= t["critical"]:
        return "critical"
    if value >= t["warning"]:
        return "warning"
    return None


def _simulate_remediation(action: str) -> str:
    # Deterministic-ish "success" simulation standing in for a real runbook
    # call (SSM Run Command / Azure Automation Runbook / Ansible playbook).
    return f"{action} executed successfully"


def evaluate_latest():
    """Look at the most recent metric row per server and raise/auto-remediate alerts."""
    raised = []
    with get_conn() as conn:
        servers = conn.execute("SELECT id FROM servers").fetchall()
        for s in servers:
            row = conn.execute(
                """SELECT * FROM metrics WHERE server_id=?
                   ORDER BY timestamp DESC LIMIT 1""",
                (s["id"],),
            ).fetchone()
            if not row:
                continue
            for metric in ("cpu_percent", "memory_percent", "disk_percent"):
                value = row[metric]
                sev = _severity(metric, value)
                if not sev:
                    continue
                now = datetime.now(timezone.utc).isoformat()
                action = None
                result = None
                if sev == "critical":
                    action = REMEDIATION_BY_METRIC[metric]
                    result = _simulate_remediation(action)
                cur = conn.execute(
                    """INSERT INTO alerts
                       (server_id, timestamp, metric, value, threshold, severity,
                        status, remediation_action, remediation_result)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        s["id"],
                        now,
                        metric,
                        value,
                        THRESHOLDS[metric][sev],
                        sev,
                        "auto-resolved" if action else "open",
                        action,
                        result,
                    ),
                )
                raised.append(cur.lastrowid)
        conn.commit()
    return raised
