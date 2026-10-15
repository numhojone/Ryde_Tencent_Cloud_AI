"""Demo login: a signed session cookie that says who is using the app. Not real authentication.

The cookie holds {"role": "rider", "rider_id": ...}, {"role": "driver", "driver_id": ..., "home": <rider session>?} or
{"role": "support"}, signed with HMAC-SHA256 using
SECRET_KEY from .env (a random per-process key when it is unset or still the placeholder, so sessions end
on restart). The server reads the rider_id from this cookie only: never from a request body, a query
parameter or the story text.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import HTTPException, Request

from app.config import settings
from app.tools.fixtures import demo_accounts, list_driver_ids, list_rider_ids

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
    return _check(data)


def _check(data: dict, nested: bool = False) -> dict | None:
    if data.get("role") == "rider" and data.get("rider_id") in list_rider_ids():
        return {"role": "rider", "rider_id": data["rider_id"], "driver_id": None, "home": None}
    if data.get("role") == "support" and not nested:
        return {"role": "support", "rider_id": None, "driver_id": None, "home": None}
    if data.get("role") == "driver" and data.get("driver_id") in list_driver_ids() and not nested:
        # home: the rider session a demo user toggled from, so toggling back needs no new login
        home = _check(data["home"], nested=True) if isinstance(data.get("home"), dict) else None
        return {"role": "driver", "rider_id": None, "driver_id": data["driver_id"], "home": home}
    return None


def cookie_payload(sess: dict) -> dict:
    """What goes into the signed cookie for a session dict."""
    out = {"role": sess["role"]}
    if sess.get("rider_id"):
        out["rider_id"] = sess["rider_id"]
    if sess.get("driver_id"):
        out["driver_id"] = sess["driver_id"]
    if sess.get("home"):
        out["home"] = cookie_payload(sess["home"])
    return out


def role_switch_allowed() -> bool:
    """The Rider | Driver toggle is a demo feature (DEMO_ROLE_SWITCH, default true for the hackathon build)."""
    return os.environ.get("DEMO_ROLE_SWITCH", "true").strip().lower() in ("1", "true", "yes", "on")


def accounts() -> list[dict]:
    """Demo rider accounts for the login picker (name + rider_id), from the rider profiles."""
    names = demo_accounts().get("riders", {})
    return [{"rider_id": rid, "name": (names.get(rid) or {}).get("name") or rid} for rid in list_rider_ids()]


def driver_accounts() -> list[dict]:
    """Demo driver accounts (name + driver_id), from the driver profiles."""
    names = demo_accounts().get("drivers", {})
    return [{"driver_id": did, "name": (names.get(did) or {}).get("name") or did} for did in list_driver_ids()]


def rider_first_name(rider_id: str | None) -> str | None:
    """The most a driver is ever told about the rider."""
    r = demo_accounts().get("riders", {}).get(rider_id or "") or {}
    return r.get("first_name")


def stories_for(rider_id: str) -> list[dict]:
    return (demo_accounts().get("riders", {}).get(rider_id) or {}).get("stories", [])


# ---------------------------------------------------------------- FastAPI dependencies

def any_session(request: Request) -> dict:
    s = verify(request.cookies.get(COOKIE))
    if s is None:
        raise HTTPException(status_code=401, detail="Sign in first")
    return s


def session(request: Request) -> dict:
    """A rider or support session. Drivers only have the driver endpoints."""
    s = any_session(request)
    if s["role"] == "driver":
        raise HTTPException(status_code=403, detail="Not available to drivers")
    return s


def driver_session(request: Request) -> dict:
    s = any_session(request)
    if s["role"] != "driver":
        raise HTTPException(status_code=403, detail="Drivers only")
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
