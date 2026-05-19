from __future__ import annotations

from urllib.parse import urlencode

from app.source_connectors.base import SourceConnector


class FindATenderConnector(SourceConnector):
    connector_name = "find_a_tender"

    def build_query(self, terms: list[str]) -> str:
        if "/api/" in (self.source.query_url or "") or "ocdsReleasePackages" in (self.source.query_url or ""):
            return self.source.query_url
        query = " ".join(term for term in terms if term).strip() or "transport technology"
        params = urlencode({"q": query[:180]})
        return f"{self.source.base_url.rstrip('/')}/api/1.0/ocdsReleasePackages?{params}"
