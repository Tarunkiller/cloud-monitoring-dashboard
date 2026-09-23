from typing import Optional
from pydantic import BaseModel


class Server(BaseModel):
    id: int
    name: str
    role: str
    is_real: bool


class Metric(BaseModel):
    id: int
    server_id: int
    timestamp: str
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    uptime_seconds: int


class LogEntry(BaseModel):
    id: int
    server_id: int
    timestamp: str
    level: str
    message: str
    is_valid: bool
    validation_note: Optional[str] = None


class Alert(BaseModel):
    id: int
    server_id: int
    timestamp: str
    metric: str
    value: float
    threshold: float
    severity: str
    status: str
    remediation_action: Optional[str] = None
    remediation_result: Optional[str] = None
