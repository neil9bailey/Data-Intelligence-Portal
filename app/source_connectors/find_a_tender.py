from __future__ import annotations

from urllib.parse import urlencode

from app.intelligence import source_query_url
from app.source_connectors.base import SourceConnector


class FindATenderConnector(SourceConnector):
    connector_name = "find_a_tender"

    def build_query(self, terms: list[str]) -> str:
        query_url = self.source.query_url or ""
        if "/api/" in query_url or "ocdsReleasePackages" in query_url:
            return source_query_url(self.source, terms)
        query = " ".join(term for term in terms if term).strip() or "transport technology"
        params = urlencode({"q": query[:180]})
        return f"{self.source.base_url.rstrip('/')}/api/1.0/ocdsReleasePackages?{params}"
