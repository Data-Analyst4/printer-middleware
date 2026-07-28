"""Dashboard session auth and optional API key checks for v1."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional, Tuple

from flask import Request, session

PUBLIC_PATHS = {"/health", "/version", "/login"}
SESSION_USER_KEY = "dashboard_user"


def dashboard_credentials() -> Tuple[Optional[str], Optional[str]]:
    user = (os.getenv("DASHBOARD_USER") or "").strip()
    password = os.getenv("DASHBOARD_PASSWORD") or ""
    if not user or not password:
        return None, None
    return user, password


def dashboard_auth_enabled() -> bool:
    user, password = dashboard_credentials()
    return bool(user and password)


def api_key_expected() -> Optional[str]:
    key = (os.getenv("API_KEY") or "").strip()
    return key or None


def flask_secret_key() -> str:
    configured = (os.getenv("SECRET_KEY") or "").strip()
    if configured:
        return configured
    user, password = dashboard_credentials()
    if user and password:
        material = f"{user}:{password}:printer-middleware-v1".encode("utf-8")
        return hashlib.sha256(material).hexdigest()
    return "dev-insecure-change-me"


def verify_dashboard_credentials(username: str, password: str) -> bool:
    expected_user, expected_password = dashboard_credentials()
    if not expected_user or expected_password is None:
        return False
    user_ok = hmac.compare_digest(username.strip(), expected_user)
    pass_ok = hmac.compare_digest(password, expected_password)
    return user_ok and pass_ok


def session_authenticated() -> bool:
    return bool(session.get(SESSION_USER_KEY))


def check_api_key(request: Request) -> bool:
    expected = api_key_expected()
    if not expected:
        return False
    provided = request.headers.get("X-API-Key") or request.args.get("api_key") or ""
    return hmac.compare_digest(provided, expected)


def request_authorized(request: Request) -> bool:
    """Allow access when auth is off, or session/API key is valid."""
    dash_on = dashboard_auth_enabled()
    api_on = bool(api_key_expected())

    if not dash_on and not api_on:
        return True
    if dash_on and session_authenticated():
        return True
    if api_on and check_api_key(request):
        return True
    return False


def login_user(username: str) -> None:
    session.clear()
    session[SESSION_USER_KEY] = username
    session.permanent = True


def logout_user() -> None:
    session.clear()
