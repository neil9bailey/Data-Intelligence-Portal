from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.automation import apply_all_preconfigured_packs, mark_interrupted_automation_runs
from app.database import (
    backup_sqlite_persistent_copy,
    engine,
    init_db,
    restore_sqlite_persistent_copy,
    retry_sqlite_locked,
    sqlite_startup_lock,
)
from app.intelligence import repair_mismatched_customer_assignments
from app.observability import configure_logging, new_request_id
from app.routes import ROUTERS
from app.seed import seed_demo_data, seed_reference_data
from app.settings import BASE_DIR, get_settings


def run_seed(seed_fn):
    with Session(engine) as session:
        seed_fn(session)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with sqlite_startup_lock():
        restore_sqlite_persistent_copy()
        init_db()
        settings = get_settings()
        if settings.seed_reference_data:
            retry_sqlite_locked(lambda: run_seed(seed_reference_data))
        if settings.seed_demo_data:
            retry_sqlite_locked(lambda: run_seed(seed_demo_data))
        if settings.auto_apply_customer_packs:
            retry_sqlite_locked(lambda: run_seed(lambda session: apply_all_preconfigured_packs(session, actor="startup-preconfigure")))
        retry_sqlite_locked(lambda: run_seed(mark_interrupted_automation_runs))
        retry_sqlite_locked(lambda: run_seed(repair_mismatched_customer_assignments))
        backup_sqlite_persistent_copy()
    try:
        yield
    finally:
        backup_sqlite_persistent_copy()


configure_logging()

app = FastAPI(title="Data Intelligence Portal", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.middleware("http")
async def persist_sqlite_copy_after_writes(request: Request, call_next):
    request_id = new_request_id(request.headers.get("x-request-id"))
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 500:
        backup_sqlite_persistent_copy()
    return response


for router in ROUTERS:
    app.include_router(router)
