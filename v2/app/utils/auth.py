"""Dashboard session auth helpers for v2."""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional

from flask import Request, session

from app.core.bootstrap import get_context

PUBLIC_PATHS = {"/health", "/version", "/login"}
SESSION_USER_KEY = "dashboard_user"


def dashboard_auth_enabled() -> bool:
    settings = get_context().settings
    return bool(settings.dashboard_user and settings.dashboard_password)


def api_key_expected() -> Optional[str]:
    return get_context().settings.api_key


def flask_secret_key() -> str:
    settings = get_context().settings
    if settings.secret_key:
        return settings.secret_key
    if settings.dashboard_user and settings.dashboard_password:
        material = (
            f"{settings.dashboard_user}:{settings.dashboard_password}:printer-middleware-v2"
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()
    return "dev-insecure-change-me"


def verify_dashboard_credentials(username: str, password: str) -> bool:
    settings = get_context().settings
    if not settings.dashboard_user or not settings.dashboard_password:
        return False
    user_ok = hmac.compare_digest(username.strip(), settings.dashboard_user)
    pass_ok = hmac.compare_digest(password, settings.dashboard_password)
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
