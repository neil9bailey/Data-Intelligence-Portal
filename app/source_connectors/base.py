from __future__ import annotations

from dataclasses import dataclass

from app.intelligence import FetchResult, detect_schema, next_page_url, parse_ocds_candidates, parse_web_candidates, source_allowed, source_query_url
from app.models import ProcurementSource


@dataclass
class SourceConnector:
    source: ProcurementSource
    connector_name: str = "generic"

    def build_query(self, terms: list[str]) -> str:
        return source_query_url(self.source, terms)

    def fetch_page(self, url: str, fetcher) -> FetchResult:
        return fetcher(url)

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
