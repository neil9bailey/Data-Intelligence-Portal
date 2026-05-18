from datetime import date

from fastapi.responses import HTMLResponse


def parse_bool(value) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def parse_optional_int(value, field_name: str, errors: list[str]) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(str(value))
    except ValueError:
        errors.append(f"{field_name} must be a valid whole number.")
        return None


def parse_float(value, field_name: str, errors: list[str], default: float = 0) -> float:
    if value in {None, ""}:
        return default
    try:
        return float(str(value))
    except ValueError:
        errors.append(f"{field_name} must be a valid number.")
        return default


def parse_optional_date(value, field_name: str, errors: list[str]) -> date | None:
    if value in {None, ""}:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        errors.append(f"{field_name} must be a valid date.")
        return None


def validation_error_response(errors: list[str], back_url: str) -> HTMLResponse:
    items = "".join(f"<li>{error}</li>" for error in errors)
    html = f"""
    <!doctype html><html><head><title>Validation error</title>
    <style>body{{font-family:Segoe UI,sans-serif;margin:40px;background:#f5f6fa;color:#15121b}}
    .panel{{max-width:780px;padding:24px;border:1px solid #ddd8e7;border-radius:8px;background:white}}</style>
    </head><body><main class="panel"><h1>Check the information</h1><ul>{items}</ul>
    <p><a href="{back_url}">Return to the previous page</a></p></main></body></html>
    """
    return HTMLResponse(html, status_code=400)
