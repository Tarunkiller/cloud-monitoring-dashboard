import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import alerts
import log_validation
import monitor
from auth import (
    LoginRequest,
    TOKEN_TTL_SECONDS,
    authenticate,
    create_access_token,
    decode_access_token,
    get_current_user,
    require_roles,
)
from database import dicts, get_conn, init_db

TICK_SECONDS = 3  # how often the fleet is sampled and pushed to connected clients


class ConnectionManager:
    """Tracks connected dashboard clients and pushes JSON snapshots to all of them."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, payload: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


def build_snapshot() -> dict:
    """One consistent read of current state — same shape as the REST endpoints,
    bundled together so the frontend doesn't need four separate round trips."""
    with get_conn() as conn:
        servers = dicts(
            conn.execute(
                """SELECT m.*, s.name as server_name FROM metrics m
                   JOIN servers s ON s.id = m.server_id
                   WHERE m.id IN (SELECT MAX(id) FROM metrics GROUP BY server_id)"""
            ).fetchall()
        )
        alert_rows = dicts(
            conn.execute(
                """SELECT a.*, s.name as server_name FROM alerts a
                   JOIN servers s ON s.id = a.server_id
                   ORDER BY a.timestamp DESC LIMIT 8"""
            ).fetchall()
        )
        log_rows = dicts(
            conn.execute(
                """SELECT l.*, s.name as server_name FROM logs l
                   JOIN servers s ON s.id = l.server_id
                   ORDER BY l.timestamp DESC LIMIT 10"""
            ).fetchall()
        )
    return {
        "type": "snapshot",
        "servers": servers,
        "alerts": alert_rows,
        "logs": log_rows,
        "log_summary": log_validation.validation_summary(),
    }


async def tick_loop():
    """The real-time engine: sample -> evaluate -> validate -> push. Runs
    forever on the server's own event loop (no separate thread, so
    broadcasting to websockets is safe without extra locking)."""
    while True:
        await asyncio.to_thread(monitor.collect_once)
        await asyncio.to_thread(alerts.evaluate_latest)
        await asyncio.to_thread(log_validation.generate_and_validate_batch, 2)
        snapshot = await asyncio.to_thread(build_snapshot)
        await manager.broadcast(snapshot)
        await asyncio.sleep(TICK_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    monitor.ensure_servers()
    monitor.collect_once()
    log_validation.generate_and_validate_batch(8)
    alerts.evaluate_latest()

    task = asyncio.create_task(tick_loop())
    yield
    task.cancel()


app = FastAPI(title="Cloud Monitoring & Automation Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """Real-time channel: pushes a fresh snapshot every TICK_SECONDS with no
    polling from the client. Sends one immediately on connect so the UI
    doesn't sit empty waiting for the next tick."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Authentication required")
        return
    try:
        decode_access_token(token)
    except HTTPException:
        await websocket.close(code=1008, reason="Invalid or expired access token")
        return

    await manager.connect(websocket)
    try:
        await websocket.send_text(json.dumps(build_snapshot()))
        while True:
            # keep the connection open; we don't expect client messages,
            # but reading lets us detect disconnects promptly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


@app.post("/api/auth/login")
def login(request: LoginRequest):
    user = authenticate(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {
        "access_token": create_access_token(user["username"], user["role"]),
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "user": user,
    }


@app.get("/api/auth/me")
def current_user(user: dict = Depends(get_current_user)):
    return user


@app.get("/api/admin/users")
def list_auth_users(_: dict = Depends(require_roles("admin"))):
    return [
        {"username": "admin", "role": "admin"},
        {"username": "operator", "role": "operator"},
        {"username": "viewer", "role": "viewer"},
    ]


@app.post("/api/operations/{action}")
def run_operation(
    action: str,
    target: str = "fleet",
    user: dict = Depends(require_roles("operator", "admin")),
):
    allowed_actions = {"clear_cache", "restart_service", "rotate_logs"}
    if action not in allowed_actions:
        raise HTTPException(status_code=400, detail="Unsupported operation")
    if user["role"] != "admin" and action != "clear_cache":
        raise HTTPException(
            status_code=403,
            detail="Operators may only clear the cache",
        )

    result_by_action = {
        "clear_cache": "Cache cleared successfully",
        "restart_service": "Service restart requested successfully",
        "rotate_logs": "Log rotation requested successfully",
    }
    result = result_by_action[action]
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO operation_audit
               (timestamp, username, role, action, target, result)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                user["sub"],
                user["role"],
                action,
                target,
                result,
            ),
        )
        conn.commit()
    return {
        "action": action,
        "target": target,
        "requested_by": user["sub"],
        "role": user["role"],
        "result": result,
    }


@app.get("/api/operations/audit")
def operation_audit(_: dict = Depends(require_roles("admin"))):
    with get_conn() as conn:
        return dicts(
            conn.execute(
                """SELECT * FROM operation_audit
                   ORDER BY timestamp DESC LIMIT 100"""
            ).fetchall()
        )


@app.get("/api/servers")
def list_servers(_: dict = Depends(require_roles("admin", "operator", "viewer"))):
    with get_conn() as conn:
        return dicts(conn.execute("SELECT * FROM servers").fetchall())


@app.get("/api/metrics/latest")
def latest_metrics(_: dict = Depends(require_roles("admin", "operator", "viewer"))):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT m.*, s.name as server_name FROM metrics m
               JOIN servers s ON s.id = m.server_id
               WHERE m.id IN (
                   SELECT MAX(id) FROM metrics GROUP BY server_id
               )"""
        ).fetchall()
        return dicts(rows)


@app.get("/api/metrics/history/{server_id}")
def metric_history(server_id: int, limit: int = 50, _: dict = Depends(require_roles("admin", "operator", "viewer"))):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM metrics WHERE server_id=?
               ORDER BY timestamp DESC LIMIT ?""",
            (server_id, limit),
        ).fetchall()
        if not rows:
            raise HTTPException(404, "no data for server")
        return dicts(rows)[::-1]


@app.get("/api/alerts")
def list_alerts(status: str | None = None, limit: int = 50, _: dict = Depends(require_roles("admin", "operator", "viewer"))):
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                """SELECT a.*, s.name as server_name FROM alerts a
                   JOIN servers s ON s.id = a.server_id
                   WHERE a.status=? ORDER BY a.timestamp DESC LIMIT ?""",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT a.*, s.name as server_name FROM alerts a
                   JOIN servers s ON s.id = a.server_id
                   ORDER BY a.timestamp DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return dicts(rows)


@app.get("/api/logs")
def list_logs(only_invalid: bool = False, limit: int = 50, _: dict = Depends(require_roles("admin", "operator", "viewer"))):
    with get_conn() as conn:
        q = """SELECT l.*, s.name as server_name FROM logs l
               JOIN servers s ON s.id = l.server_id"""
        if only_invalid:
            q += " WHERE l.is_valid=0"
        q += " ORDER BY l.timestamp DESC LIMIT ?"
        rows = conn.execute(q, (limit,)).fetchall()
        return dicts(rows)


@app.get("/api/logs/summary")
def logs_summary(_: dict = Depends(require_roles("admin", "operator", "viewer"))):
    return log_validation.validation_summary()


@app.get("/api/health")
def health():
    return {"status": "ok", "connected_clients": len(manager.active)}
