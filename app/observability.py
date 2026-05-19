from __future__ import annotations

from contextvars import ContextVar
import logging
import uuid


request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s request_id=%(request_id)s %(name)s %(message)s",
    )
    request_filter = RequestIdFilter()
    for handler in logging.getLogger().handlers:
        if not any(isinstance(item, RequestIdFilter) for item in handler.filters):
            handler.addFilter(request_filter)


def new_request_id(value: str | None = None) -> str:
    request_id = (value or "").strip() or uuid.uuid4().hex
    request_id_var.set(request_id)
    return request_id


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(item, RequestIdFilter) for item in logger.filters):
        logger.addFilter(RequestIdFilter())
    return logger
