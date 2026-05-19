from __future__ import annotations

import base64
import json
import os
from urllib import parse, request


def _principal_header() -> str:
    admin_group_id = os.getenv("ENTRA_ADMIN_GROUP_ID", "")
    principal = {
        "name": os.getenv("DIP_TRIGGER_ACTOR_NAME", "Azure automation trigger"),
        "claims": [
            {"typ": "preferred_username", "val": os.getenv("DIP_TRIGGER_ACTOR", "azure-automation-trigger")},
            {"typ": "name", "val": os.getenv("DIP_TRIGGER_ACTOR_NAME", "Azure automation trigger")},
        ],
    }
    if admin_group_id:
        principal["claims"].append({"typ": "groups", "val": admin_group_id})
    encoded = base64.b64encode(json.dumps(principal, separators=(",", ":")).encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def main() -> int:
    endpoint = os.getenv("DIP_INTERNAL_ADMIN_AUTOMATION_URL", "http://127.0.0.1:8080/admin/automation/run")
    body = parse.urlencode(
        {
            "export_format": os.getenv("DIP_TRIGGER_EXPORT_FORMAT", "pdf"),
            "email_recipients": os.getenv("DIP_TRIGGER_EMAIL_RECIPIENTS", ""),
        }
    ).encode("utf-8")
    trigger_request = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "x-ms-client-principal": _principal_header(),
        },
    )
    with request.urlopen(trigger_request, timeout=30) as response:
        print(f"HTTP {response.status} {response.geturl()}")
        print(response.read(500).decode("utf-8", errors="ignore"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
