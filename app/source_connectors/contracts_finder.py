from __future__ import annotations

from urllib.parse import urlencode

from app.source_connectors.base import SourceConnector


class ContractsFinderConnector(SourceConnector):
    connector_name = "contracts_finder"

    def build_query(self, terms: list[str]) -> str:
        if "Published/Notices/OCDS/Search" in (self.source.query_url or ""):
            return self.source.query_url
        query = " ".join(term for term in terms if term).strip() or "transport technology"
        params = urlencode({"keyword": query[:180], "limit": "50"})
        return f"{self.source.base_url.rstrip('/')}/Published/Notices/OCDS/Search?{params}"
