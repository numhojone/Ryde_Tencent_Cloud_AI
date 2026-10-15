"""Demo login: a signed session cookie that says who is using the app. Not real authentication.

The cookie holds {"role": "rider", "rider_id": ...} or {"role": "support"}, signed with HMAC-SHA256 using
SECRET_KEY from .env (a random per-process key when it is unset or still the placeholder, so sessions end
on restart). The server reads the rider_id from this cookie only: never from a request body, a query
parameter or the story text.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException, Request

from app.config import settings
from app.tools.fixtures import demo_accounts, list_rider_ids

COOKIE = "rr_session"
MAX_AGE = 12 * 3600
_KEY = (settings.secret_key if settings.secret_key and settings.secret_key != "change_me"
        else secrets.token_hex(32)).encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: dict) -> str:
    body = _b64(json.dumps({**payload, "iat": int(time.time())}, separators=(",", ":")).encode())
    mac = hmac.new(_KEY, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def verify(token: str | None) -> dict | None:
    """The session, or None if the cookie is missing, tampered with or expired."""
    if not token or "." not in token:
        return None
    body, mac = token.rsplit(".", 1)
    if not hmac.compare_digest(mac, hmac.new(_KEY, body.encode(), hashlib.sha256).hexdigest()):
        return None
    try:
        data = json.loads(_unb64(body))
    except Exception:  # noqa: BLE001
        return None
    if time.time() - int(data.get("iat", 0)) > MAX_AGE:
        return None
    if data.get("role") == "rider" and data.get("rider_id") in list_rider_ids():
        return {"role": "rider", "rider_id": data["rider_id"]}
    if data.get("role") == "support":
        return {"role": "support", "rider_id": None}
    return None


def accounts() -> list[dict]:
    """Demo rider accounts for the login picker (name + rider_id), from the rider profiles."""
    names = demo_accounts().get("riders", {})
    return [{"rider_id": rid, "name": (names.get(rid) or {}).get("name") or rid} for rid in list_rider_ids()]


def stories_for(rider_id: str) -> list[dict]:
    return (demo_accounts().get("riders", {}).get(rider_id) or {}).get("stories", [])


# ---------------------------------------------------------------- FastAPI dependencies

def session(request: Request) -> dict:
    s = verify(request.cookies.get(COOKIE))
    if s is None:
        raise HTTPException(status_code=401, detail="Sign in first")
    return s


def rider_session(request: Request) -> dict:
    s = session(request)
    if s["role"] != "rider":
        raise HTTPException(status_code=403, detail="Only a rider can do this")
    return s


def support_session(request: Request) -> dict:
    s = session(request)
    if s["role"] != "support":
        raise HTTPException(status_code=403, detail="Support agents only")
    return s
