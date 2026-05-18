from fastapi import APIRouter
from fastapi.responses import Response

from app.settings import get_settings


router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"status": "ok", "app": get_settings().app_name}


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
