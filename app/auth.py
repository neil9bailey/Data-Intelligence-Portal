from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.settings import get_settings


@dataclass(frozen=True)
class CurrentUser:
    name: str = "Local user"
    username: str = "local-user"
    groups: tuple[str, ...] = ()
    role: str = "local-admin"
    authenticated: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role in {"admin", "local-admin"}


def _decode_client_principal(value: str) -> dict:
    if not value:
        return {}
    padded = value + "=" * (-len(value) % 4)
    try:
        return json.loads(base64.b64decode(padded).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}


def _claim_values(principal: dict, claim_names: set[str]) -> list[str]:
    values: list[str] = []
    for claim in principal.get("claims") or []:
        claim_type = str(claim.get("typ") or claim.get("type") or "")
        if claim_type in claim_names:
            value = str(claim.get("val") or claim.get("value") or "")
            if value:
                values.append(value)
    return values


def get_current_user(request: Request) -> CurrentUser:
    settings = get_settings()
    if not settings.entra_auth_enabled:
        return CurrentUser()

    principal = _decode_client_principal(request.headers.get("x-ms-client-principal", ""))
    if not principal:
        return CurrentUser(name="Unauthenticated", username="unknown", role="unauthenticated")

    groups = tuple(
        _claim_values(principal, {"groups", "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"})
    )
    usernames = _claim_values(
        principal,
        {
            "preferred_username",
            "upn",
            "email",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
        },
    )
    names = _claim_values(principal, {"name", "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"})
    role = "authenticated"
    if settings.entra_admin_group_id and settings.entra_admin_group_id in groups:
        role = "admin"
    elif settings.entra_standard_group_id and settings.entra_standard_group_id in groups:
        role = "standard"

    return CurrentUser(
        name=names[0] if names else str(principal.get("name") or "Signed-in user"),
        username=usernames[0] if usernames else str(principal.get("user_id") or "signed-in-user"),
        groups=groups,
        role=role,
        authenticated=True,
    )


def require_admin(request: Request) -> CurrentUser:
    user = get_current_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access is required.")
    return user
