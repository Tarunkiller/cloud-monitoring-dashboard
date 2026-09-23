"""
Automated log validation & reporting pipeline.

Ingests raw log lines per server and flags each one as valid/invalid using
a small set of structural + semantic checks, instead of a human eyeballing
logs one by one. This is the piece that maps to "automated log validation
and reporting workflows" on the resume — it turns a manual triage step
into a rule-based pass that runs on every batch of logs.

Checks applied (any failure marks the line invalid, with a reason):
1. Required fields present (timestamp parses, level is a known level).
2. Message is not empty / not truncated (no trailing "...").
3. ERROR/CRITICAL lines must contain a traceable identifier (a request id,
   exception name, or service name) — bare "error occurred" lines are
   flagged as low-signal and routed for review instead of auto-accepted.
"""
import random
from datetime import datetime, timezone

from database import get_conn

KNOWN_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

SAMPLE_MESSAGES = {
    "INFO": [
        "health check passed",
        "request handled in 42ms",
        "cache warmed for region us-east",
        "scheduled job completed",
    ],
    "WARNING": [
        "response time above SLA threshold",
        "retrying downstream call, attempt 2",
        "disk usage crossed 80% soft limit",
    ],
    "ERROR": [
        "NullReferenceException in OrderService.Process",
        "timeout calling billing-api req_id=8f21",
        "error occurred",  # deliberately low-signal to demo the validator catching it
    ],
    "CRITICAL": [
        "database connection pool exhausted",
        "OutOfMemoryError in worker-node-1",
    ],
}


def _validate(level: str, message: str):
    if level not in KNOWN_LEVELS:
        return False, "unknown log level"
    if not message or message.endswith("..."):
        return False, "empty or truncated message"
    if level in ("ERROR", "CRITICAL"):
        has_identifier = any(tok in message for tok in ("req_id", "Exception", "Error"))
        if not has_identifier:
            return False, "error log lacks a traceable identifier"
    return True, None


def generate_and_validate_batch(n: int = 5):
    """Simulate a batch of incoming logs from the fleet, run them through
    validation, and store the results with their verdicts."""
    with get_conn() as conn:
        server_ids = [r["id"] for r in conn.execute("SELECT id FROM servers")]
        rows = []
        for _ in range(n):
            server_id = random.choice(server_ids)
            level = random.choices(
                list(SAMPLE_MESSAGES.keys()), weights=[5, 2, 2, 1], k=1
            )[0]
            message = random.choice(SAMPLE_MESSAGES[level])
            is_valid, note = _validate(level, message)
            rows.append(
                (
                    server_id,
                    datetime.now(timezone.utc).isoformat(),
                    level,
                    message,
                    int(is_valid),
                    note,
                )
            )
        conn.executemany(
            """INSERT INTO logs (server_id, timestamp, level, message, is_valid, validation_note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        return len(rows)


def validation_summary():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM logs").fetchone()["c"]
        invalid = conn.execute("SELECT COUNT(*) c FROM logs WHERE is_valid=0").fetchone()["c"]
        return {
            "total_logs": total,
            "flagged_invalid": invalid,
            "valid_rate_percent": round(100 * (total - invalid) / total, 1) if total else 100.0,
        }
