"""Dashboard user accounts stored in SQLite."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from app.db.database import DatabaseManager

VALID_ROLES = ("admin", "operator")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{3,64}$")

_db: Optional[DatabaseManager] = None


def _get_db() -> DatabaseManager:
    global _db
    if _db is None:
        _db = DatabaseManager()
    return _db


def _now() -> str:
    return datetime.now().isoformat()


def _row_to_user(row: Dict[str, Any], include_hash: bool = False) -> Dict[str, Any]:
    user = {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_hash:
        user["password_hash"] = row["password_hash"]
    return user


def count_users() -> int:
    with _get_db().get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        return int(row["c"] if row else 0)


def count_active_admins() -> int:
    with _get_db().get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND is_active = 1"
        ).fetchone()
        return int(row["c"] if row else 0)


def list_users() -> List[Dict[str, Any]]:
    with _get_db().get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY username COLLATE NOCASE ASC"
        ).fetchall()
        return [_row_to_user(dict(r)) for r in rows]


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with _get_db().get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(dict(row)) if row else None


def get_user_by_username(username: str, include_hash: bool = False) -> Optional[Dict[str, Any]]:
    with _get_db().get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
            (username.strip(),),
        ).fetchone()
        return _row_to_user(dict(row), include_hash=include_hash) if row else None


def verify_user_credentials(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_username(username, include_hash=True)
    if not user or not user.get("is_active"):
        return None
    if not check_password_hash(user["password_hash"], password):
        return None
    user.pop("password_hash", None)
    return user


def _validate_username(username: str) -> Optional[str]:
    cleaned = (username or "").strip()
    if not USERNAME_RE.match(cleaned):
        return "Username must be 3-64 chars: letters, numbers, . _ -"
    return None


def _validate_password(password: str) -> Optional[str]:
    if not password or len(password) < 6:
        return "Password must be at least 6 characters"
    return None


def _validate_role(role: str) -> Optional[str]:
    if role not in VALID_ROLES:
        return f"Role must be one of: {', '.join(VALID_ROLES)}"
    return None


def create_user(username: str, password: str, role: str = "operator") -> Dict[str, Any]:
    err = _validate_username(username) or _validate_password(password) or _validate_role(role)
    if err:
        return {"success": False, "error": err}

    cleaned = username.strip()
    if get_user_by_username(cleaned):
        return {"success": False, "error": "Username already exists"}

    now = _now()
    password_hash = generate_password_hash(password)
    with _get_db().get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (cleaned, password_hash, role, now, now),
        )
        user_id = int(cur.lastrowid)

    return {"success": True, "user": get_user_by_id(user_id)}


def update_user(
    user_id: int,
    *,
    password: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Dict[str, Any]:
    existing = get_user_by_id(user_id)
    if not existing:
        return {"success": False, "error": "User not found"}

    new_role = existing["role"]
    if role is not None:
        err = _validate_role(role)
        if err:
            return {"success": False, "error": err}
        new_role = role

    new_active = existing["is_active"] if is_active is None else bool(is_active)

    # Prevent removing the last active admin
    if existing["role"] == "admin" and existing["is_active"]:
        demoting = new_role != "admin" or not new_active
        if demoting and count_active_admins() <= 1:
            return {"success": False, "error": "Cannot remove or demote the last active admin"}

    password_hash = None
    if password is not None and password != "":
        err = _validate_password(password)
        if err:
            return {"success": False, "error": err}
        password_hash = generate_password_hash(password)

    now = _now()
    with _get_db().get_connection() as conn:
        if password_hash is not None:
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?, role = ?, is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (password_hash, new_role, 1 if new_active else 0, now, user_id),
            )
        else:
            conn.execute(
                """
                UPDATE users
                SET role = ?, is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_role, 1 if new_active else 0, now, user_id),
            )

    return {"success": True, "user": get_user_by_id(user_id)}


def delete_user(user_id: int) -> Dict[str, Any]:
    existing = get_user_by_id(user_id)
    if not existing:
        return {"success": False, "error": "User not found"}

    if existing["role"] == "admin" and existing["is_active"] and count_active_admins() <= 1:
        return {"success": False, "error": "Cannot delete the last active admin"}

    with _get_db().get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    return {"success": True}


def ensure_seed_admin() -> Optional[Dict[str, Any]]:
    """Create first admin from DASHBOARD_USER / DASHBOARD_PASSWORD when DB is empty."""
    if count_users() > 0:
        return None

    username = (os.getenv("DASHBOARD_USER") or "").strip()
    password = os.getenv("DASHBOARD_PASSWORD") or ""
    if not username or not password:
        return None

    result = create_user(username, password, role="admin")
    if result.get("success"):
        return result.get("user")
    return None
