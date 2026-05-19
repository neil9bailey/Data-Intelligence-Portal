from app.source_connectors.base import SourceConnector
from app.source_connectors.contracts_finder import ContractsFinderConnector
from app.source_connectors.find_a_tender import FindATenderConnector


def connector_for_source(source) -> SourceConnector:
    key = (source.source_key or "").strip().lower()
    base = (source.base_url or source.query_url or "").lower()
    if key == "contracts_finder" or "contractsfinder.service.gov.uk" in base:
        return ContractsFinderConnector(source, connector_name="contracts_finder")
    if key == "find_a_tender" or "find-tender.service.gov.uk" in base:
        return FindATenderConnector(source, connector_name="find_a_tender")
    return SourceConnector(source)
