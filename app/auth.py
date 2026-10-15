"""Demo login: a signed session cookie that says which rider is using the app. Not real authentication.

There is one role: rider. The support console and the driver view are demo panes inside the signed-in rider's
own screen, scoped to that rider's own cases; nobody signs in as a driver or a support agent.

The cookie holds {"role": "rider", "rider_id": ...}, signed with HMAC-SHA256 using SECRET_KEY from .env (a random
per-process key when it is unset or still the placeholder, so sessions end on restart). The server reads the
rider_id from this cookie only: never from a request body, a query parameter or the story text.
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
from app.tools.fixtures import first_name, list_rider_ids, person_name

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
    """The session, or None if the cookie is missing, tampered with, expired, or not a known rider."""
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
    return None


def accounts() -> list[dict]:
    """The riders who can sign in: the six rider profiles, with the name each profile carries."""
    return [{"rider_id": rid, "name": person_name(rid) or rid} for rid in list_rider_ids()]


def display(rider_id: str) -> str:
    """'Wong Mei Ling (R-3312)', as in the rider's profile."""
    return f"{person_name(rider_id) or rider_id} ({rider_id})"


def rider_first_name(rider_id: str | None) -> str | None:
    """The most a driver is ever told about the rider."""
    return first_name(person_name(rider_id))


def session(request: Request) -> dict:
    s = verify(request.cookies.get(COOKIE))
    if s is None:
        raise HTTPException(status_code=401, detail="Sign in first")
    return s


# One role: every data endpoint takes the signed-in rider.
rider_session = session
