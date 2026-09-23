"""
SQLite persistence layer for the Cloud Monitoring & Automation Dashboard.

Tables:
- servers: the fleet of "cloud" nodes being watched (one real node = this
  host, plus simulated nodes so the dashboard looks like a multi-server
  environment).
- metrics: time-series CPU / memory / disk / uptime samples per server.
- logs: raw log lines ingested from each server, with a validation flag
  set by the log-validation pipeline (backend/log_validation.py).
- alerts: threshold breaches raised by the rule engine, plus whether an
  automated remediation action was taken and its outcome.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "monitoring.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL,
    is_real INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL REFERENCES servers(id),
    timestamp TEXT NOT NULL,
    cpu_percent REAL NOT NULL,
    memory_percent REAL NOT NULL,
    disk_percent REAL NOT NULL,
    uptime_seconds INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_server_time ON metrics(server_id, timestamp);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL REFERENCES servers(id),
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    is_valid INTEGER NOT NULL DEFAULT 1,
    validation_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_logs_server_time ON logs(server_id, timestamp);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL REFERENCES servers(id),
    timestamp TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    threshold REAL NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    remediation_action TEXT,
    remediation_result TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_server_time ON alerts(server_id, timestamp);

CREATE TABLE IF NOT EXISTS operation_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    username TEXT NOT NULL,
    role TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    result TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_operation_audit_time ON operation_audit(timestamp);
"""


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def dicts(rows):
    return [dict(r) for r in rows]
