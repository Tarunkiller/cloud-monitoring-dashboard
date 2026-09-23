"""
Collects system-health metrics.

The host this API runs on is monitored for real via psutil (CPU, memory,
disk, uptime). Two additional "cloud nodes" are simulated with a random
walk so the dashboard reads like a small fleet, which is what most
monitoring dashboards (Datadog, CloudWatch, Azure Monitor) actually show.
"""
import random
import time
from datetime import datetime, timezone

import psutil

from database import get_conn

# in-memory random-walk state for simulated servers: {server_id: (cpu, mem, disk)}
_sim_state: dict[int, list[float]] = {}


def ensure_servers():
    with get_conn() as conn:
        cur = conn.execute("SELECT id, name FROM servers")
        existing = {row["name"] for row in cur.fetchall()}
        seed = [
            ("host-local", "primary-api", 1),
            ("web-node-1", "web-frontend", 0),
            ("worker-node-1", "batch-worker", 0),
        ]
        for name, role, is_real in seed:
            if name not in existing:
                conn.execute(
                    "INSERT INTO servers (name, role, is_real) VALUES (?, ?, ?)",
                    (name, role, is_real),
                )
        conn.commit()


def _real_host_sample():
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    uptime = int(time.time() - psutil.boot_time())
    return cpu, mem, disk, uptime


def _simulated_sample(server_id: int):
    state = _sim_state.setdefault(server_id, [30.0, 40.0, 55.0])
    for i in range(3):
        drift = random.uniform(-6, 8)  # slight upward bias so alerts fire sometimes
        state[i] = min(99.0, max(3.0, state[i] + drift))
    uptime = int(time.time()) % 900000  # fake but monotonic-ish within a run
    return state[0], state[1], state[2], uptime


def collect_once():
    """Take one sample for every server and write it to the metrics table."""
    with get_conn() as conn:
        servers = conn.execute("SELECT id, name, is_real FROM servers").fetchall()
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for s in servers:
            if s["is_real"]:
                cpu, mem, disk, uptime = _real_host_sample()
            else:
                cpu, mem, disk, uptime = _simulated_sample(s["id"])
            rows.append((s["id"], now, round(cpu, 1), round(mem, 1), round(disk, 1), uptime))
        conn.executemany(
            """INSERT INTO metrics (server_id, timestamp, cpu_percent, memory_percent,
               disk_percent, uptime_seconds) VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        return rows
