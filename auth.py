import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

JWT_SECRET = os.getenv("JWT_SECRET", "change-this-development-secret")
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "3600"))
security = HTTPBearer(auto_error=False)

USERS = {
    "admin": {"password": os.getenv("ADMIN_PASSWORD", "admin123"), "role": "admin"},
    "operator": {"password": os.getenv("OPERATOR_PASSWORD", "operator123"), "role": "operator"},
    "viewer": {"password": os.getenv("VIEWER_PASSWORD", "viewer123"), "role": "viewer"},
}


class LoginRequest(BaseModel):
    username: str
    password: str


def _encode(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode(value: str) -> dict:
    padded = value + "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode()))


def create_access_token(username: str, role: str) -> str:
    header = _encode({"alg": "HS256", "typ": "JWT"})
    payload = _encode(
        {"sub": username, "role": role, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    )
    unsigned = f"{header}.{payload}"
    signature = hmac.new(JWT_SECRET.encode(), unsigned.encode(), hashlib.sha256).digest()
    return f"{unsigned}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def decode_access_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".")
        unsigned = f"{header}.{payload}"
        expected = hmac.new(JWT_SECRET.encode(), unsigned.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        claims = _decode(payload)
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("invalid signature")
        if claims.get("exp", 0) < int(time.time()):
            raise ValueError("expired token")
        if claims.get("sub") not in USERS or claims.get("role") != USERS[claims["sub"]]["role"]:
            raise ValueError("invalid user")
        return claims
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, base64.binascii.Error):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def authenticate(username: str, password: str) -> dict | None:
    user = USERS.get(username)
    if not user or not secrets.compare_digest(user["password"], password):
        return None
    return {"username": username, "role": user["role"]}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)


def require_roles(*allowed_roles: str) -> Callable:
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return dependency
