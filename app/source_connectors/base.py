from __future__ import annotations

from dataclasses import dataclass
from time import sleep

from app.intelligence import FetchResult, detect_schema, next_page_url, parse_ocds_candidates, parse_web_candidates, source_allowed, source_query_url
from app.models import ProcurementSource


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass
class SourceConnector:
    source: ProcurementSource
    connector_name: str = "generic"
    max_retries: int = 2
    retry_backoff_seconds: float = 0.15
    max_retry_after_seconds: float = 1.0

    def build_query(self, terms: list[str]) -> str:
        return source_query_url(self.source, terms)

    def fetch_page(self, url: str, fetcher) -> FetchResult:
        attempts = 0
        last_fetch = fetcher(url)
        while self._should_retry(last_fetch, attempts):
            attempts += 1
            pause = self._retry_pause(last_fetch, attempts)
            if pause > 0:
                sleep(pause)
            last_fetch = fetcher(url)
        if attempts:
            suffix = f" Retried {attempts} time(s)."
            last_fetch.error = f"{last_fetch.error}{suffix}".strip() if last_fetch.error else suffix.strip()
        return last_fetch

    def parse_candidates(self, fetch: FetchResult, terms: list[str]):
        if not fetch.ok:
            return []
        candidates = parse_ocds_candidates(fetch.text, self.source)
        if candidates:
            return candidates
        return parse_web_candidates(fetch.text, self.source, terms)

    def next_page(self, fetch: FetchResult) -> str:
        url = next_page_url(fetch.text) if fetch.ok else ""
        return url if url and source_allowed(url) else ""

    def detect_schema(self, fetch: FetchResult) -> str:
        return detect_schema(fetch.text, fetch.content_type) if fetch.ok else "unknown"

    def run_summary(self, fetch: FetchResult, page_count: int = 1, pagination_stopped: bool = False) -> str:
        if fetch.ok:
            suffix = " Pagination stopped at configured limit." if pagination_stopped else ""
            return f"{self.connector_name} checked {page_count} page(s); HTTP {fetch.status_code}.{suffix}"
        if fetch.status_code == 429:
            return f"{self.connector_name} rate limited by provider; HTTP 429. Retry later or reduce source run volume."
        if fetch.status_code >= 500:
            return f"{self.connector_name} provider/server failure; HTTP {fetch.status_code}."
        return f"{self.connector_name} failed: {fetch.error or 'unknown error'}"

    def _should_retry(self, fetch: FetchResult, attempts: int) -> bool:
        return attempts < self.max_retries and fetch.status_code in RETRYABLE_STATUS_CODES

    def _retry_pause(self, fetch: FetchResult, attempt: int) -> float:
        if fetch.retry_after_seconds is not None:
            return max(0.0, min(fetch.retry_after_seconds, self.max_retry_after_seconds))
        return min(self.retry_backoff_seconds * attempt, self.max_retry_after_seconds)
