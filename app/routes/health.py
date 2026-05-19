from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from app.database import database_mode, engine
from app.settings import BASE_DIR, get_settings



router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"status": "ok", "app": get_settings().app_name}


@router.get("/readyz")
def readyz():
    checks = {
        "database": "unknown",
        "templates": "ok" if (BASE_DIR / "templates").exists() else "missing",
        "static": "ok" if (BASE_DIR / "static").exists() else "missing",
    }
    status_code = 200
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"failed: {str(exc)[:160]}"
        status_code = 503
    if checks["templates"] != "ok" or checks["static"] != "ok":
        status_code = 503
    return JSONResponse(
        {
            "status": "ok" if status_code == 200 else "not_ready",
            "app": get_settings().app_name,
            "database_mode": database_mode(),
            "checks": checks,
        },
        status_code=status_code,
    )


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
