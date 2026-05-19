from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from html import unescape
import json
import re
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlparse, urlunparse
from xml.etree import ElementTree

import httpx
from sqlmodel import Session, col, select

from app.audit import compact_snapshot, log_event
from app.llm import LLMError, generate_llm_text, kra_system_prompt, llm_enabled
from app.models import (
    Customer,
    CustomerWatchProfile,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    KRAAgentProfile,
    KRAFinding,
    KRAResearchRun,
    NewsFeedItem,
    NewsFeedSource,
    Opportunity,
    OpportunityDocument,
    OpportunityMatchEvidence,
    ProcurementSource,
    SourceCheckSnapshot,
)
from app.requirement_taxonomy import assess_requirement_confidence, classify_requirement_category, requirement_themes_for_text as taxonomy_requirement_themes_for_text
from app.rule_loader import load_rule_file
from app.settings import get_settings


MANAGED_STATUSES = {"", "new", "award_notice", "early_engagement", "needs_review"}
GENERIC_CUSTOMER_TERM_MARKERS = {"context", "to be confirmed", "programme teams", "regional", "sponsor"}
SHORT_ALIAS_ALLOWLIST = {"tfl", "iot", "5g"}
GENERIC_MATCH_TERMS = {
    "he",
    "nh",
    "nr",
    "uk",
    "it",
    "the",
    "and",
    "for",
    "other",
    "public",
    "sector",
    "services",
    "service",
    "transport",
}
DEFAULT_NOTICE_LOOKBACK_DAYS = 180
DEFAULT_NOTICE_PAGE_LIMIT = 100
DEFAULT_NOTICE_MAX_PAGES = 8
MARKET_RELEVANCE_THRESHOLD = 44
AI_PROMPT_VERSION = "kra-summary-v1"
CONTRACTS_FINDER_V2_SEARCH_URL = "https://www.contractsfinder.service.gov.uk/api/rest/2/search_notices/json"
PUBLIC_MARKET_SEARCH_KEYWORDS = [
    "cyber security",
    "IT services",
    "managed IT support",
    "service desk",
    "network services",
    "operational technology",
    "SCADA",
    "communications infrastructure",
    "mass communication",
    "telecommunications",
    "traffic management",
    "roadside technology",
    "passenger information",
    "ticketing",
    "CCTV",
    "security systems",
    "fleet telemetry",
    "IoT telemetry",
]
GLOBAL_CAPABILITY_TERMS = [
    "asset management system",
    "communications infrastructure",
    "cyber security",
    "cctv",
    "digital services",
    "fare collection",
    "fleet telemetry",
    "high availability",
    "it services",
    "it support",
    "iot telemetry",
    "managed it support",
    "mass communication",
    "microsoft 365",
    "network communications",
    "network services",
    "operational technology",
    "passenger information",
    "roadside technology",
    "scada",
    "service management platform",
    "service desk",
    "security systems",
    "telecommunications",
    "ticketing",
    "traffic management",
]
HIGH_SIGNAL_CAPABILITY_TERMS = {
    "communications infrastructure",
    "cyber security",
    "cctv",
    "fare collection",
    "fleet telemetry",
    "it services",
    "it support",
    "iot telemetry",
    "managed it support",
    "mass communication",
    "microsoft 365",
    "network communications",
    "network services",
    "operational technology",
    "passenger information",
    "roadside technology",
    "scada",
    "service desk",
    "security systems",
    "telecommunications",
    "ticketing",
    "traffic management",
}
LOW_VALUE_MARKET_NOISE_TERMS = {
    "drinking-water",
    "firewater pump",
    "fm services",
    "forestry",
    "insurance cover",
    "journey of recycling",
    "laser cutter",
    "leadership development",
    "mobile partitions",
    "musical equipment",
    "outdoor and tactical equipment",
    "passenger assistant",
    "prison education",
    "raked seating",
    "racking systems",
    "refurbishment",
    "retroreflectivity",
    "road marking",
    "road markings",
    "self-employment training",
    "strip-out",
    "surfacing",
    "suspended ceiling",
    "building in use support",
    "taxi and mpv",
    "topographic survey",
    "traffic signs",
    "window cleaning",
}


@dataclass
class FetchResult:
    ok: bool
    status_code: int
    url: str
    text: str
    content_type: str = ""
    error: str = ""


@dataclass
class CandidateOpportunity:
    title: str
    buyer_name: str = ""
    notice_identifier: str = ""
    ocid: str = ""
    notice_type: str = ""
    procurement_stage: str = ""
    published_date: date | None = None
    deadline_date: date | None = None
    value_high: float = 0
    currency: str = "GBP"
    cpv_codes: str = ""
    source_url: str = ""
    summary: str = ""
    content_hash: str = ""


def source_rules() -> dict:
    return load_rule_file("sources.yml")


def extraction_rules() -> dict:
    return load_rule_file("extraction.yml")


def approved_domains() -> set[str]:
    guardrails = source_rules().get("guardrails") or {}
    return {str(domain).lower() for domain in guardrails.get("approved_domains") or []}


def source_allowed(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.netloc.lower() in approved_domains()


def textish(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def strip_html(value: str) -> str:
    cleaned = re.sub(r"<script.*?</script>", " ", value or "", flags=re.I | re.S)
    cleaned = re.sub(r"<style.*?</style>", " ", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return textish(unescape(cleaned))


def split_terms(value: str) -> list[str]:
    terms: list[str] = []
    for item in re.split(r"[,;\n]+", value or ""):
        cleaned = textish(item).lower()
        if cleaned and cleaned not in terms:
            terms.append(cleaned)
    return terms


def content_hash(text: str) -> str:
    return sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def parse_dateish(value: object) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def numberish(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def source_query_url(source: ProcurementSource, terms: list[str]) -> str:
    query = " ".join(terms[:8]) or "transport technology framework"
    now = datetime.now(UTC)
    start = now - timedelta(days=DEFAULT_NOTICE_LOOKBACK_DAYS)
    values = {
        "query": quote_plus(query),
        "published_from": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "published_to": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated_from": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated_to": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "limit": str(DEFAULT_NOTICE_PAGE_LIMIT),
    }
    url = source.query_url
    for key, value in values.items():
        url = url.replace(f"{{{key}}}", value)
    if source.source_key == "contracts_finder" and "publishedFrom=" not in url:
        return append_query_params(
            url,
            {
                "publishedFrom": values["published_from"],
                "publishedTo": values["published_to"],
                "stages": "planning,tender",
                "limit": str(DEFAULT_NOTICE_PAGE_LIMIT),
            },
        )
    if source.source_key == "find_a_tender" and "updatedFrom=" not in url:
        return append_query_params(
            url,
            {
                "updatedFrom": values["updated_from"],
                "updatedTo": values["updated_to"],
                "stages": "planning,tender",
                "limit": str(DEFAULT_NOTICE_PAGE_LIMIT),
            },
        )
    return url


def append_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in params.items():
        query.setdefault(key, value)
    return urlunparse(parsed._replace(query=urlencode(query)))


def next_page_url(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ""
    links = payload.get("links") if isinstance(payload, dict) else None
    if isinstance(links, dict):
        return textish(links.get("next"))
    return ""


def fetch_error_message(status_code: int, headers: httpx.Headers) -> str:
    if status_code in {403, 429, 503}:
        retry_after = headers.get("retry-after")
        retry_detail = f"; retry after {retry_after} seconds" if retry_after else ""
        return f"HTTP {status_code} rate/service limit{retry_detail}"
    return f"HTTP {status_code}"


def fetch_source_url(url: str) -> FetchResult:
    if not source_allowed(url):
        return FetchResult(False, 0, url, "", error="Blocked by approved-source allow-list.")
    try:
        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            response = client.get(
                url,
                headers={
                    "User-Agent": "Data Intelligence Portal KRA local agent",
                    "Accept": "application/json,text/html,text/plain,*/*",
                },
            )
        final_url = str(response.url)
        if not source_allowed(final_url):
            return FetchResult(False, response.status_code, final_url, "", error="Redirected outside approved domains.")
        return FetchResult(
            response.status_code < 400,
            response.status_code,
            final_url,
            response.text or "",
            response.headers.get("content-type", ""),
            "" if response.status_code < 400 else fetch_error_message(response.status_code, response.headers),
        )
    except httpx.HTTPError as exc:
        return FetchResult(False, 0, url, "", error=f"Source check failed: {exc}")


def parse_feed_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def child_text(element: ElementTree.Element, names: tuple[str, ...]) -> str:
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return textish(found.text)
    return ""


def parse_feed_items(text: str, feed_url: str, limit: int = 8) -> list[dict[str, object]]:
    if not text.strip():
        return []
    root = ElementTree.fromstring(text.encode("utf-8"))
    if root.tag.endswith("rss"):
        entries = root.findall("./channel/item")
        title_names = ("title",)
        summary_names = ("description",)
        date_names = ("pubDate",)
        link_names = ("link",)
    else:
        ns = "{http://www.w3.org/2005/Atom}"
        entries = root.findall(f"{ns}entry")
        title_names = (f"{ns}title", "title")
        summary_names = (f"{ns}summary", f"{ns}content", "summary", "content")
        date_names = (f"{ns}updated", f"{ns}published", "updated", "published")
        link_names = ()

    items: list[dict[str, object]] = []
    for entry in entries[:limit]:
        title = child_text(entry, title_names)
        summary = strip_html(child_text(entry, summary_names))
        published_at = parse_feed_datetime(child_text(entry, date_names))
        link = ""
        if link_names:
            link = child_text(entry, link_names)
        else:
            for node in entry.findall("{http://www.w3.org/2005/Atom}link") + entry.findall("link"):
                href = node.attrib.get("href", "")
                rel = node.attrib.get("rel", "alternate")
                if href and rel in {"alternate", ""}:
                    link = href
                    break
        link = urljoin(feed_url, link)
        if title and link:
            items.append(
                {
                    "title": title,
                    "summary": summary[:700],
                    "link": link,
                    "published_at": published_at,
                    "content_hash": content_hash(f"{title}|{link}|{summary}"),
                }
            )
    return items


def refresh_news_feed(session: Session, feed: NewsFeedSource, limit: int = 8) -> int:
    before = compact_snapshot(feed)
    fetch = fetch_source_url(feed.feed_url)
    feed.last_checked_at = datetime.now(UTC)
    feed.last_status = "ok" if fetch.ok else fetch.error or f"HTTP {fetch.status_code}"
    created = 0
    if fetch.ok:
        try:
            for item in parse_feed_items(fetch.text, feed.feed_url, limit):
                existing = session.exec(select(NewsFeedItem).where(NewsFeedItem.link == str(item["link"]))).first()
                if existing:
                    existing.title = str(item["title"])
                    existing.summary = str(item["summary"])
                    existing.published_at = item["published_at"]  # type: ignore[assignment]
                    existing.content_hash = str(item["content_hash"])
                    existing.updated_at = datetime.now(UTC)
                    session.add(existing)
                    continue
                session.add(
                    NewsFeedItem(
                        feed_source_id=feed.id,
                        title=str(item["title"]),
                        link=str(item["link"]),
                        summary=str(item["summary"]),
                        published_at=item["published_at"],  # type: ignore[arg-type]
                        content_hash=str(item["content_hash"]),
                    )
                )
                created += 1
        except ElementTree.ParseError as exc:
            feed.last_status = f"Feed parse failed: {exc}"
    session.add(feed)
    log_event(
        session,
        entity_type="NewsFeedSource",
        entity_id=feed.id,
        action="refresh",
        summary=f"Refreshed news feed {feed.name}; {created} new item(s)",
        before=before,
        after=feed,
    )
    session.commit()
    return created


def refresh_news_feeds(session: Session, limit_per_feed: int = 8) -> int:
    feeds = list(session.exec(select(NewsFeedSource).where(NewsFeedSource.active == True)))  # noqa: E712
    return sum(refresh_news_feed(session, feed, limit_per_feed) for feed in feeds)


def detect_schema(text: str, content_type: str = "") -> str:
    sample = (text or "")[:5000].lower()
    if "json" in content_type.lower() or "releases" in sample or "compiledrelease" in sample:
        return "ocds_json"
    if "xml" in content_type.lower() or "eforms" in sample:
        return "eforms_or_xml"
    if "<html" in sample or "<a " in sample:
        return "html"
    return "unknown"


def failure_schema(fetch: FetchResult) -> str:
    error = (fetch.error or "").lower()
    if "allow-list" in error or "outside approved domains" in error:
        return "guardrail_blocked"
    if "rate" in error or "too many" in error or fetch.status_code in {403, 429, 503}:
        return "rate_limited"
    if "certificate" in error or "ssl" in error:
        return "tls_error"
    if fetch.status_code:
        return "http_error"
    if error:
        return "network_error"
    return "unknown"


def record_snapshot(session: Session, source: ProcurementSource, fetch: FetchResult, query_url: str) -> SourceCheckSnapshot:
    latest = session.exec(
        select(SourceCheckSnapshot)
        .where(SourceCheckSnapshot.source_id == source.id)
        .order_by(col(SourceCheckSnapshot.checked_at).desc())
    ).first()
    current_hash = content_hash(fetch.text) if fetch.ok else ""
    previous_hash = latest.content_hash if latest else ""
    if not fetch.ok:
        change_type = "failed"
    elif not latest:
        change_type = "first_seen"
    elif previous_hash != current_hash:
        change_type = "changed"
    else:
        change_type = "unchanged"
    snapshot = SourceCheckSnapshot(
        source_id=source.id,
        query_url=query_url,
        ok=fetch.ok,
        status_code=fetch.status_code,
        content_hash=current_hash,
        previous_hash=previous_hash,
        change_type=change_type,
        detected_schema=detect_schema(fetch.text, fetch.content_type) if fetch.ok else failure_schema(fetch),
        connector_status=source.connector_status,
        notes=fetch.error or source.last_status,
    )
    session.add(snapshot)
    session.flush()
    log_event(
        session,
        entity_type="SourceCheckSnapshot",
        entity_id=snapshot.id,
        action="create",
        summary=f"Recorded {change_type} source snapshot for {source.name}",
        after=snapshot,
    )
    return snapshot


def iter_ocds_releases(payload: object):
    if isinstance(payload, list):
        for item in payload:
            yield from iter_ocds_releases(item)
        return
    if not isinstance(payload, dict):
        return
    releases = payload.get("releases")
    if isinstance(releases, list):
        for release in releases:
            if isinstance(release, dict):
                yield release
    for key in ["packages", "records", "results", "data"]:
        values = payload.get(key)
        if isinstance(values, list):
            for item in values:
                yield from iter_ocds_releases(item)
    compiled = payload.get("compiledRelease")
    if isinstance(compiled, dict):
        yield compiled


def candidate_hash(source: ProcurementSource, title: str, identifier: str, summary: str) -> str:
    return content_hash(f"{source.id}|{identifier}|{title}|{summary}")


def candidate_source_url(source: ProcurementSource, release: dict, identifier: str) -> str:
    links = release.get("links") if isinstance(release.get("links"), dict) else {}
    link = textish(links.get("self") or release.get("url"))
    if link:
        return link
    if source.source_key == "contracts_finder":
        match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", identifier)
        if match:
            return f"{source.base_url.rstrip('/')}/notice/{match.group(0)}"
    if source.source_key == "find_a_tender":
        match = re.search(r"\d{6}-\d{4}", identifier)
        if match:
            return f"{source.base_url.rstrip('/')}/Notice/{match.group(0)}"
    return source.base_url


def candidate_from_release(release: dict, source: ProcurementSource) -> CandidateOpportunity | None:
    tender = release.get("tender") if isinstance(release.get("tender"), dict) else {}
    planning = release.get("planning") if isinstance(release.get("planning"), dict) else {}
    buyer = release.get("buyer") if isinstance(release.get("buyer"), dict) else {}
    value = tender.get("value") if isinstance(tender.get("value"), dict) else {}
    tender_period = tender.get("tenderPeriod") if isinstance(tender.get("tenderPeriod"), dict) else {}
    title = textish(tender.get("title") or planning.get("rationale") or release.get("id") or release.get("ocid"))
    if not title:
        return None
    summary_parts = [textish(tender.get("description") or planning.get("rationale") or "")]
    identifier = textish(release.get("id") or release.get("ocid") or title)
    tags = release.get("tag") if isinstance(release.get("tag"), list) else []
    cpv: list[str] = []
    classification = tender.get("classification") if isinstance(tender.get("classification"), dict) else {}
    label = " - ".join(part for part in [textish(classification.get("id")), textish(classification.get("description"))] if part)
    if label:
        cpv.append(label)
    for lot in tender.get("lots") or []:
        if not isinstance(lot, dict):
            continue
        summary_parts.append(textish(lot.get("title") or ""))
        summary_parts.append(textish(lot.get("description") or ""))
    for item in tender.get("items") or []:
        if not isinstance(item, dict):
            continue
        classification = item.get("classification") if isinstance(item.get("classification"), dict) else {}
        label = " - ".join(part for part in [textish(classification.get("id")), textish(classification.get("description"))] if part)
        if label:
            cpv.append(label)
        for additional in item.get("additionalClassifications") or []:
            if not isinstance(additional, dict):
                continue
            label = " - ".join(part for part in [textish(additional.get("id")), textish(additional.get("description"))] if part)
            if label:
                cpv.append(label)
    if not textish(buyer.get("name")):
        for party in release.get("parties") or []:
            if isinstance(party, dict) and "buyer" in (party.get("roles") or []):
                buyer = {"name": party.get("name")}
                break
    summary = textish(" ".join(part for part in summary_parts if part))
    return CandidateOpportunity(
        title=title[:250],
        buyer_name=textish(buyer.get("name")),
        notice_identifier=identifier[:250],
        ocid=textish(release.get("ocid")),
        notice_type=", ".join(textish(tag) for tag in tags if textish(tag))[:250],
        procurement_stage=textish(tender.get("status") or (tags[0] if tags else ""))[:120],
        published_date=parse_dateish(release.get("date")),
        deadline_date=parse_dateish(tender_period.get("endDate")),
        value_high=numberish(value.get("amount")),
        currency=textish(value.get("currency") or "GBP")[:12],
        cpv_codes="; ".join(cpv)[:500],
        source_url=candidate_source_url(source, release, identifier),
        summary=summary[:2000],
        content_hash=candidate_hash(source, title, identifier, summary),
    )


def parse_ocds_candidates(text: str, source: ProcurementSource) -> list[CandidateOpportunity]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    candidates: list[CandidateOpportunity] = []
    seen: set[str] = set()
    for release in iter_ocds_releases(payload):
        candidate = candidate_from_release(release, source)
        if not candidate:
            continue
        key = candidate.notice_identifier or candidate.content_hash
        if key not in seen:
            seen.add(key)
            candidates.append(candidate)
    return candidates


def parse_web_candidates(text: str, source: ProcurementSource, terms: list[str]) -> list[CandidateOpportunity]:
    candidates: list[CandidateOpportunity] = []
    seen: set[str] = set()
    for match in re.finditer(r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", text or "", re.I | re.S):
        href, label_html = match.groups()
        title = strip_html(label_html)
        if len(title) < 8:
            continue
        url = urljoin(source.base_url, unescape(href))
        if not source_allowed(url):
            continue
        combined = f"{title} {url}".lower()
        if not any(term in combined for term in terms) and "notice" not in combined:
            continue
        identifier = url.rstrip("/").rsplit("/", 1)[-1]
        if identifier in seen:
            continue
        seen.add(identifier)
        candidates.append(
            CandidateOpportunity(
                title=title[:250],
                notice_identifier=identifier[:250],
                source_url=url,
                summary=title,
                content_hash=candidate_hash(source, title, identifier, title),
            )
        )
    return candidates


def candidate_from_contracts_finder_v2_item(item: dict, source: ProcurementSource, keyword: str) -> CandidateOpportunity:
    notice_id = str(item.get("id") or item.get("noticeIdentifier") or "").strip()
    title = textish(str(item.get("title") or "Untitled Contracts Finder opportunity"))
    description = strip_html(str(item.get("description") or ""))
    cpv = textish(
        " ".join(
            str(item.get(key) or "")
            for key in ("cpvDescription", "cpvDescriptionExpanded", "cpvCodes", "cpvCodesExtended")
        )
    )
    source_url = f"{source.base_url.rstrip('/')}/notice/{notice_id}" if notice_id else source.base_url
    notice_status = textish(str(item.get("noticeStatus") or ""))
    notice_type = textish(str(item.get("noticeType") or "Contract"))
    value_high = numberish(item.get("valueHigh")) or numberish(item.get("valueLow")) or numberish(item.get("awardedValue"))
    digest = content_hash("|".join([notice_id, title, description, str(item.get("lastNotifableUpdate") or "")]))
    return CandidateOpportunity(
        title=title,
        buyer_name=textish(str(item.get("organisationName") or "")),
        notice_identifier=textish(str(item.get("noticeIdentifier") or notice_id)),
        ocid="",
        notice_type=notice_type,
        procurement_stage=notice_status or notice_type,
        published_date=parse_dateish(item.get("publishedDate")),
        deadline_date=parse_dateish(item.get("deadlineDate") or item.get("approachMarketDate")),
        value_high=value_high,
        currency="GBP",
        cpv_codes=cpv,
        source_url=source_url,
        summary=description,
        content_hash=digest,
    )


def run_public_market_keyword_sweep(
    session: Session,
    keywords: list[str] | None = None,
    limit_per_keyword: int = 60,
    poster=None,
) -> dict[str, int | list[str]]:
    """Read-only Contracts Finder v2 search used to enrich the demo with current opportunity signals."""
    source = session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "contracts_finder")).first()
    if not source:
        source = ProcurementSource(
            source_key="contracts_finder",
            name="Contracts Finder OCDS search API",
            source_family="official_notice",
            source_type="ocds_api",
            base_url="https://www.contractsfinder.service.gov.uk",
            query_url=(
                "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
                "?publishedFrom={published_from}&publishedTo={published_to}&stages=planning,tender&limit={limit}"
            ),
            official=True,
            active=True,
            coverage="UK below-threshold, future, live, early engagement and award notices",
            auth_model="public reads",
            data_format="REST OCDS JSON and public v2 notice search",
            dedupe_strategy="ocid_or_notice_id",
            connector_status="live_mvp",
            notes="Official Contracts Finder opportunity source.",
        )
        session.add(source)
        session.flush()
    post = poster or httpx.post
    created = updated = skipped = 0
    errors: list[str] = []
    published_from = (datetime.now(UTC) - timedelta(days=DEFAULT_NOTICE_LOOKBACK_DAYS)).strftime("%d/%m/%Y")
    for keyword in keywords or PUBLIC_MARKET_SEARCH_KEYWORDS:
        payload = {
            "searchCriteria": {
                "types": ["Contract", "Pipeline"],
                "keyword": keyword,
                "publishedFrom": published_from,
            },
            "size": limit_per_keyword,
        }
        try:
            response = post(CONTRACTS_FINDER_V2_SEARCH_URL, json=payload, timeout=30)
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code >= 400:
                errors.append(f"{keyword}: HTTP {status_code}")
                continue
            data = response.json()
        except Exception as exc:
            errors.append(f"{keyword}: {str(exc)[:160]}")
            continue
        for row in data.get("noticeList") or []:
            item = row.get("item") or row
            if not isinstance(item, dict):
                skipped += 1
                continue
            candidate = candidate_from_contracts_finder_v2_item(item, source, keyword)
            if is_award_candidate(candidate) or not is_current_candidate(candidate):
                skipped += 1
                continue
            relevance, rationale = market_relevance_for_candidate(candidate)
            if relevance < MARKET_RELEVANCE_THRESHOLD:
                skipped += 1
                continue
            opportunity, was_created = upsert_opportunity(session, source, candidate, relevance, rationale)
            created += 1 if was_created else 0
            updated += 0 if was_created else 1
            document = session.exec(
                select(OpportunityDocument).where(
                    OpportunityDocument.opportunity_id == opportunity.id,
                    OpportunityDocument.url_or_path == opportunity.source_url,
                )
            ).first()
            if not document:
                document = OpportunityDocument(
                    opportunity_id=opportunity.id or 0,
                    title=f"Contracts Finder notice: {opportunity.title[:120]}",
                    document_type="public_notice",
                    url_or_path=opportunity.source_url,
                    retrieval_status="linked",
                    human_review_status="review_required",
                    platform_name="Contracts Finder",
                    content_summary=opportunity.summary[:1200],
                )
                session.add(document)
                session.flush()
            create_requirements_for_opportunity(session, opportunity, textish(f"{opportunity.title}. {opportunity.summary}. {opportunity.cpv_codes}"))
    session.commit()
    return {"keywords": len(keywords or PUBLIC_MARKET_SEARCH_KEYWORDS), "created": created, "updated": updated, "skipped": skipped, "errors": errors[:8]}


def _specific_customer_terms(customer: Customer) -> list[str]:
    raw_terms = [customer.customer_name, customer.aliases, customer.buying_entities]
    terms: list[str] = []
    for value in raw_terms:
        for term in split_terms(value):
            cleaned = term.lower()
            if any(marker in cleaned for marker in GENERIC_CUSTOMER_TERM_MARKERS):
                continue
            if len(cleaned) < 4 and cleaned not in SHORT_ALIAS_ALLOWLIST:
                continue
            if cleaned not in terms:
                terms.append(cleaned)
    return terms


def normalise_match_terms(terms: list[str]) -> list[str]:
    cleaned_terms: list[str] = []
    for term in terms:
        cleaned = textish(term).lower()
        if not cleaned:
            continue
        if cleaned in GENERIC_MATCH_TERMS:
            continue
        if len(cleaned) < 4 and cleaned not in SHORT_ALIAS_ALLOWLIST:
            continue
        if cleaned not in cleaned_terms:
            cleaned_terms.append(cleaned)
    return cleaned_terms


def _term_in_text(term: str, text: str) -> bool:
    if " " in term:
        return term in text
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def candidate_matches_customer(candidate: CandidateOpportunity, customer: Customer) -> bool:
    terms = _specific_customer_terms(customer)
    if not terms:
        return False
    buyer_text = candidate.buyer_name.lower()
    if buyer_text:
        return any(_term_in_text(term, buyer_text) for term in terms)
    combined = " ".join([candidate.title, candidate.summary, candidate.source_url]).lower()
    return any(_term_in_text(term, combined) for term in terms)


def watch_profile_terms(session: Session, profile: CustomerWatchProfile | None = None, customer: Customer | None = None) -> list[str]:
    values: list[str] = []
    if profile:
        values.extend([profile.profile_name, profile.buyer_aliases, profile.keywords, profile.cpv_codes, profile.domains])
        if profile.customer_id:
            customer = session.get(Customer, profile.customer_id)
    if customer:
        values.extend([customer.customer_name, customer.aliases, customer.buying_entities, customer.domain, customer.sector])
    terms: list[str] = []
    for value in values:
        for term in split_terms(value):
            if term not in terms:
                terms.append(term)
    return normalise_match_terms(terms) or ["technology", "framework"]


def relevance_for_candidate(candidate: CandidateOpportunity, terms: list[str]) -> tuple[float, str]:
    combined = " ".join([candidate.title, candidate.buyer_name, candidate.summary, candidate.cpv_codes]).lower()
    matched = [term for term in normalise_match_terms(terms) if _term_in_text(term, combined)]
    if not matched:
        return 0, "No watch terms matched."
    return float(min(100, 20 + len(matched) * 12)), f"Matched terms: {', '.join(matched[:8])}."


def is_award_candidate(candidate: CandidateOpportunity) -> bool:
    category = f"{candidate.notice_type} {candidate.procurement_stage} {candidate.title}".lower()
    return "award" in category or candidate.procurement_stage.lower() in {"complete", "completed"}


def is_current_candidate(candidate: CandidateOpportunity) -> bool:
    status_text = f"{candidate.notice_type} {candidate.procurement_stage}".lower()
    if any(term in status_text for term in ("closed", "complete", "completed", "cancelled", "withdrawn")):
        return False
    if candidate.deadline_date and candidate.deadline_date < date.today():
        return False
    return True


def has_capability_match(candidate: CandidateOpportunity) -> bool:
    combined = " ".join([candidate.title, candidate.summary, candidate.cpv_codes]).lower()
    return any(_term_in_text(term, combined) for term in GLOBAL_CAPABILITY_TERMS)


def market_relevance_for_candidate(candidate: CandidateOpportunity) -> tuple[float, str]:
    combined = " ".join([candidate.title, candidate.buyer_name, candidate.summary, candidate.cpv_codes]).lower()
    if any(term in combined for term in LOW_VALUE_MARKET_NOISE_TERMS):
        return 0, "Filtered out as a low-value market-noise match."
    matched = [term for term in GLOBAL_CAPABILITY_TERMS if _term_in_text(term, combined)]
    strong = [term for term in matched if term in HIGH_SIGNAL_CAPABILITY_TERMS]
    if not strong and len(matched) < 2:
        return 0, "No strong capability terms matched."
    score = min(100, 44 + len(strong) * 14 + (len(matched) - len(strong)) * 6)
    return float(score), f"Public sector market signal matched capability terms: {', '.join(matched[:8])}."


def inferred_opportunity_status(candidate: CandidateOpportunity) -> str:
    category = f"{candidate.notice_type} {candidate.procurement_stage} {candidate.title}".lower()
    if "award" in category or candidate.procurement_stage.lower() in {"complete", "completed"}:
        return "award_notice"
    if "planning" in category or "early engagement" in category or "pipeline" in category:
        return "early_engagement"
    return "new"


def upsert_opportunity(
    session: Session,
    source: ProcurementSource,
    candidate: CandidateOpportunity,
    relevance_score: float,
    rationale: str,
    customer_id: int | None = None,
    business_unit_id: int | None = None,
) -> tuple[Opportunity, bool]:
    existing = None
    if candidate.ocid:
        existing = session.exec(select(Opportunity).where(Opportunity.ocid == candidate.ocid)).first()
    if not existing and candidate.source_url and candidate.source_url.rstrip("/") != source.base_url.rstrip("/"):
        existing = session.exec(select(Opportunity).where(Opportunity.source_url == candidate.source_url)).first()
    if not existing and candidate.notice_identifier:
        existing = session.exec(
            select(Opportunity).where(
                Opportunity.source_id == source.id,
                Opportunity.notice_identifier == candidate.notice_identifier,
            )
        ).first()
    if not existing and candidate.content_hash:
        existing = session.exec(select(Opportunity).where(Opportunity.content_hash == candidate.content_hash)).first()
    created = existing is None
    opportunity = existing or Opportunity(source_id=source.id, title=candidate.title)
    before = compact_snapshot(opportunity) if existing else ""
    opportunity.source_id = source.id
    if customer_id is not None:
        opportunity.customer_id = customer_id
    if business_unit_id is not None:
        opportunity.business_unit_id = business_unit_id
    opportunity.title = candidate.title
    opportunity.buyer_name = candidate.buyer_name
    opportunity.notice_identifier = candidate.notice_identifier
    opportunity.ocid = candidate.ocid
    opportunity.notice_type = candidate.notice_type
    opportunity.procurement_stage = candidate.procurement_stage
    opportunity.published_date = candidate.published_date
    opportunity.deadline_date = candidate.deadline_date
    opportunity.value_high = candidate.value_high
    opportunity.currency = candidate.currency or "GBP"
    opportunity.cpv_codes = candidate.cpv_codes
    opportunity.source_url = candidate.source_url
    opportunity.summary = candidate.summary
    if created or opportunity.status in MANAGED_STATUSES:
        opportunity.status = inferred_opportunity_status(candidate)
    opportunity.relevance_score = relevance_score
    opportunity.relevance_rationale = rationale
    opportunity.content_hash = candidate.content_hash
    opportunity.updated_at = datetime.now(UTC)
    session.add(opportunity)
    session.flush()
    log_event(
        session,
        entity_type="Opportunity",
        entity_id=opportunity.id,
        action="create" if created else "update",
        summary=f"{'Created' if created else 'Updated'} opportunity {opportunity.title}",
        before=before,
        after=opportunity,
    )
    record_match_evidence(session, opportunity, rationale, relevance_score)
    return opportunity, created


def record_match_evidence(session: Session, opportunity: Opportunity, rationale: str, relevance_score: float) -> None:
    if not opportunity.id:
        return
    existing = session.exec(
        select(OpportunityMatchEvidence).where(
            OpportunityMatchEvidence.opportunity_id == opportunity.id,
            OpportunityMatchEvidence.evidence_type == "classification_rationale",
        )
    ).first()
    matched_term = ""
    match = re.search(r"matched(?: capability terms)?:\s*([^.;]+)", rationale or "", re.I)
    if match:
        matched_term = match.group(1)[:180]
    evidence = existing or OpportunityMatchEvidence(opportunity_id=opportunity.id, evidence_type="classification_rationale")
    evidence.customer_id = opportunity.customer_id
    evidence.business_unit_id = opportunity.business_unit_id
    evidence.matched_term = matched_term
    evidence.source_field = "title/buyer/summary/cpv"
    evidence.score_delta = relevance_score
    evidence.rationale = rationale[:1000]
    session.add(evidence)


def repair_mismatched_customer_assignments(session: Session) -> int:
    repaired = 0
    opportunities = list(session.exec(select(Opportunity).where(Opportunity.customer_id != None)))  # noqa: E711
    for opportunity in opportunities:
        customer = session.get(Customer, opportunity.customer_id) if opportunity.customer_id else None
        if not customer:
            continue
        candidate = CandidateOpportunity(
            title=opportunity.title,
            buyer_name=opportunity.buyer_name,
            notice_identifier=opportunity.notice_identifier,
            ocid=opportunity.ocid,
            notice_type=opportunity.notice_type,
            procurement_stage=opportunity.procurement_stage,
            source_url=opportunity.source_url,
            summary=opportunity.summary,
            cpv_codes=opportunity.cpv_codes,
        )
        if candidate_matches_customer(candidate, customer):
            continue
        before = compact_snapshot(opportunity)
        customer_name = customer.customer_name
        opportunity.customer_id = None
        opportunity.business_unit_id = None
        opportunity.status = "needs_review"
        opportunity.relevance_score = 0
        opportunity.relevance_rationale = (
            f"Unassigned by data-quality repair: buyer/text did not match {customer_name} aliases. "
            f"Previous assignment was {customer_name}."
        )
        opportunity.updated_at = datetime.now(UTC)
        session.add(opportunity)
        log_event(
            session,
            entity_type="Opportunity",
            entity_id=opportunity.id,
            action="data_quality_repair",
            summary=f"Unassigned mismatched opportunity from {customer_name}",
            before=before,
            after=opportunity,
        )
        repaired += 1
    if repaired:
        session.commit()
    return repaired


def repair_low_quality_market_opportunities(session: Session) -> int:
    repaired = 0
    opportunities = list(session.exec(select(Opportunity).where(Opportunity.customer_id == None)))  # noqa: E711
    for opportunity in opportunities:
        candidate = CandidateOpportunity(
            title=opportunity.title,
            buyer_name=opportunity.buyer_name,
            notice_identifier=opportunity.notice_identifier,
            ocid=opportunity.ocid,
            notice_type=opportunity.notice_type,
            procurement_stage=opportunity.procurement_stage,
            published_date=opportunity.published_date,
            deadline_date=opportunity.deadline_date,
            value_high=opportunity.value_high,
            currency=opportunity.currency,
            cpv_codes=opportunity.cpv_codes,
            source_url=opportunity.source_url,
            summary=opportunity.summary,
            content_hash=opportunity.content_hash,
        )
        relevance, rationale = market_relevance_for_candidate(candidate)
        should_hold_back = is_award_candidate(candidate) or not is_current_candidate(candidate) or relevance < MARKET_RELEVANCE_THRESHOLD
        old_rationale = opportunity.relevance_rationale or ""
        needs_rationale_refresh = old_rationale.startswith("Capability-market match for ") or "Search keyword:" in opportunity.summary
        if should_hold_back:
            if opportunity.relevance_score == 0 and opportunity.status == "needs_review":
                continue
            before = compact_snapshot(opportunity)
            opportunity.status = "needs_review"
            opportunity.relevance_score = 0
            opportunity.relevance_rationale = "Held back from executive pack by market-quality gate: insufficient current capability match."
        elif needs_rationale_refresh or abs(float(opportunity.relevance_score or 0) - relevance) > 0.1:
            before = compact_snapshot(opportunity)
            opportunity.relevance_score = relevance
            opportunity.relevance_rationale = rationale
        else:
            continue
        opportunity.updated_at = datetime.now(UTC)
        session.add(opportunity)
        log_event(
            session,
            entity_type="Opportunity",
            entity_id=opportunity.id,
            action="data_quality_repair",
            summary=f"Rechecked market opportunity quality gate for {opportunity.title}",
            before=before,
            after=opportunity,
        )
        repaired += 1
    if repaired:
        session.commit()
    return repaired


def requirement_themes_for_text(text: str) -> list[str]:
    return taxonomy_requirement_themes_for_text(text)


def create_requirements_for_opportunity(session: Session, opportunity: Opportunity, source_text: str) -> int:
    count = 0
    themes = requirement_themes_for_text(source_text) or ["general opportunity fit"]
    for theme in themes:
        existing = session.exec(
            select(ExtractedRequirement).where(
                ExtractedRequirement.opportunity_id == opportunity.id,
                ExtractedRequirement.requirement_theme == theme,
            )
        ).first()
        if existing:
            continue
        category = classify_requirement_category(source_text, theme)
        confidence, confidence_reason = assess_requirement_confidence(
            source_text,
            theme=theme,
            category=category,
            customer_id=opportunity.customer_id,
            opportunity_id=opportunity.id,
            source_reference=opportunity.source_url,
        )
        requirement = ExtractedRequirement(
            opportunity_id=opportunity.id,
            customer_id=opportunity.customer_id,
            requirement_theme=theme,
            requirement_category=category,
            requirement_text=source_text[:6000],
            requirement_source=opportunity.source_url,
            confidence=confidence,
            confidence_reason=confidence_reason,
        )
        session.add(requirement)
        session.flush()
        count += 1
        log_event(
            session,
            entity_type="ExtractedRequirement",
            entity_id=requirement.id,
            action="create",
            summary=f"Created requirement theme {theme}",
            after=requirement,
        )
    return count


def extract_quality_questions(text: str) -> list[tuple[str, str]]:
    rules = extraction_rules()
    markers = [str(item).lower() for item in rules.get("quality_question_markers") or []]
    patterns = [re.compile(str(pattern), re.I) for pattern in rules.get("weighting_patterns") or []]
    questions: list[tuple[str, str]] = []
    for line in re.split(r"[\r\n]+", text or ""):
        cleaned = textish(line)
        if len(cleaned) < 12:
            continue
        lower = cleaned.lower()
        looks_like_question = "?" in cleaned or any(marker in lower for marker in markers)
        weighting = ""
        for pattern in patterns:
            match = pattern.search(cleaned)
            if match:
                weighting = match.group(0)
                break
        if looks_like_question or weighting:
            questions.append((cleaned[:1200], weighting))
    return questions[:30]


def extract_document_intelligence(session: Session, opportunity: Opportunity, document: OpportunityDocument, text: str) -> tuple[int, int]:
    source_text = textish(f"{document.title}. {document.content_summary}. {document.notes}. {text}")
    requirement_count = create_requirements_for_opportunity(session, opportunity, source_text)
    question_count = 0
    for question_text, weighting in extract_quality_questions(source_text):
        existing = session.exec(
            select(ExtractedQualityQuestion).where(
                ExtractedQualityQuestion.opportunity_id == opportunity.id,
                ExtractedQualityQuestion.question_text == question_text,
            )
        ).first()
        if existing:
            continue
        themes = requirement_themes_for_text(question_text)
        theme = themes[0] if themes else "bid quality response"
        category = classify_requirement_category(question_text, theme)
        confidence, confidence_reason = assess_requirement_confidence(
            question_text,
            theme=theme,
            category=category,
            customer_id=opportunity.customer_id,
            opportunity_id=opportunity.id,
            source_reference=document.url_or_path or opportunity.source_url,
            weighting=weighting,
        )
        question = ExtractedQualityQuestion(
            opportunity_id=opportunity.id or 0,
            customer_id=opportunity.customer_id,
            document_id=document.id,
            section_reference=document.document_type,
            question_text=question_text,
            weighting=weighting,
            requirement_theme=theme,
            requirement_category=category,
            confidence=confidence,
            confidence_reason=confidence_reason,
        )
        session.add(question)
        session.flush()
        question_count += 1
        log_event(
            session,
            entity_type="ExtractedQualityQuestion",
            entity_id=question.id,
            action="create",
            summary=f"Extracted quality question for opportunity {opportunity.id}",
            after=question,
        )
    return requirement_count, question_count


def run_source_check(session: Session, source_id: int, fetcher=fetch_source_url) -> SourceCheckSnapshot:
    source = session.get(ProcurementSource, source_id)
    if not source:
        raise ValueError(f"Source {source_id} not found")
    from app.source_connectors import connector_for_source

    connector = connector_for_source(source)
    url = connector.build_query(["transport", "technology", "framework"])
    fetch = connector.fetch_page(url, fetcher)
    before = compact_snapshot(source)
    source.last_checked_at = datetime.now(UTC)
    source.last_status = f"HTTP {fetch.status_code}" if fetch.ok else (fetch.error or "failed")
    source.connector_status = f"{connector.connector_name}_checked" if fetch.ok else "warning"
    session.add(source)
    snapshot = record_snapshot(session, source, fetch, url)
    log_event(session, entity_type="ProcurementSource", entity_id=source.id, action="update", summary=f"Checked source {source.name}", before=before, after=source)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def run_kra_research(
    session: Session,
    agent_profile_id: int | None = None,
    source_id: int | None = None,
    source_ids: list[int] | None = None,
    customer_id: int | None = None,
    query: str = "",
    fetcher=fetch_source_url,
) -> KRAResearchRun:
    agent = session.get(KRAAgentProfile, agent_profile_id) if agent_profile_id else session.exec(select(KRAAgentProfile)).first()
    customer = session.get(Customer, customer_id) if customer_id else None
    if source_id:
        sources = [session.get(ProcurementSource, source_id)]
    elif source_ids is not None:
        sources = [session.get(ProcurementSource, item) for item in source_ids]
    else:
        sources = list(session.exec(select(ProcurementSource).where(ProcurementSource.active == True)))  # noqa: E712
    sources = [source for source in sources if source]
    run = KRAResearchRun(
        agent_profile_id=agent.id if agent else None,
        source_id=source_id,
        customer_id=customer_id,
        query=query,
        status="started",
        guardrail_summary=(
            "KRA local run. Approved public HTTPS sources only; no portal login, customer contact, "
            "submission, bid/no-bid, legal or compliance decisioning."
        ),
    )
    session.add(run)
    session.flush()
    terms = split_terms(query) + watch_profile_terms(session, customer=customer) + GLOBAL_CAPABILITY_TERMS
    findings_created = 0
    candidate_brief_items: list[str] = []
    for source in sources:
        from app.source_connectors import connector_for_source

        connector = connector_for_source(source)
        url = connector.build_query(terms)
        for page_number in range(DEFAULT_NOTICE_MAX_PAGES):
            if not url:
                break
            run.sources_checked += 1
            fetch = connector.fetch_page(url, fetcher)
            source.last_checked_at = datetime.now(UTC)
            source.last_status = f"HTTP {fetch.status_code}" if fetch.ok else (fetch.error or "failed")
            session.add(source)
            snapshot = record_snapshot(session, source, fetch, url)
            finding = KRAFinding(
                run_id=run.id,
                source_id=source.id,
                customer_id=customer_id,
                finding_type="source_change" if snapshot.change_type == "changed" else "source_observation",
                title=f"{source.name}: {snapshot.change_type}",
                summary=(
                    f"Detected schema {snapshot.detected_schema}; status {snapshot.status_code}; "
                    f"connector {source.connector_status}; source URL {url}."
                ),
                source_url=url,
                content_hash=snapshot.content_hash,
                confidence="high" if fetch.ok else "low",
                change_status=snapshot.change_type,
            )
            session.add(finding)
            findings_created += 1
            if not fetch.ok:
                break
            candidates = connector.parse_candidates(fetch, terms)
            for candidate in candidates[:80]:
                direct_customer_match = bool(customer and candidate_matches_customer(candidate, customer))
                relevance, rationale = relevance_for_candidate(candidate, terms)
                if direct_customer_match and relevance < 70:
                    relevance = 70
                    rationale = f"Buyer matched {customer.customer_name}; {rationale}"
                if customer and not direct_customer_match:
                    relevance, rationale = market_relevance_for_candidate(candidate)
                    if (
                        is_award_candidate(candidate)
                        or not is_current_candidate(candidate)
                        or relevance < MARKET_RELEVANCE_THRESHOLD
                    ):
                        continue
                elif relevance <= 0:
                    continue
                opportunity, _ = upsert_opportunity(
                    session,
                    source,
                    candidate,
                    relevance,
                    rationale,
                    customer_id=customer.id if direct_customer_match and customer else customer_id if not customer else None,
                    business_unit_id=customer.business_unit_id if customer else None,
                )
                candidate_brief_items.append(
                    f"{candidate.title} | buyer {candidate.buyer_name or 'not detected'} | "
                    f"stage {candidate.procurement_stage or candidate.notice_type or 'not detected'} | "
                    f"relevance {relevance:g}"
                )
                create_requirements_for_opportunity(session, opportunity, textish(f"{candidate.title}. {candidate.summary}. {candidate.cpv_codes}"))
            next_url = connector.next_page(fetch)
            url = next_url if next_url and page_number + 1 < DEFAULT_NOTICE_MAX_PAGES else ""
    if llm_enabled():
        try:
            settings = get_settings()
            source_context = "\n".join(candidate_brief_items[:15])
            user_prompt = "\n".join(
                [
                    f"Customer: {customer.customer_name if customer else 'All customers'}",
                    f"Research query: {query or 'No query supplied'}",
                    f"Sources checked: {run.sources_checked}",
                    "Candidate opportunities:",
                    source_context,
                    "",
                    "Create a concise live-demo briefing with: key signals, data-quality warnings, likely next human actions, and report readiness.",
                ]
            )
            system_prompt = kra_system_prompt()
            summary = generate_llm_text(
                system_prompt,
                user_prompt,
                max_output_tokens=650,
            )
            finding = KRAFinding(
                run_id=run.id,
                customer_id=customer_id,
                finding_type="ai_research_summary",
                title="KRA AI briefing summary",
                summary=f"{summary}\n\nRequires human review before onward use.",
                confidence="medium",
                change_status="ai_assisted",
                human_review_status="pending",
                provider=settings.kra_llm_provider,
                model=settings.kra_model,
                prompt_version=AI_PROMPT_VERSION,
                system_prompt_hash=content_hash(system_prompt),
                user_prompt_hash=content_hash(user_prompt),
                source_context_hash=content_hash(source_context),
                output_hash=content_hash(summary),
            )
            session.add(finding)
            findings_created += 1
        except LLMError as exc:
            run.error_summary = f"AI summary unavailable: {str(exc)[:220]}"
    run.status = "completed"
    run.findings_created = findings_created
    run.finished_at = datetime.now(UTC)
    session.add(run)
    log_event(session, entity_type="KRAResearchRun", entity_id=run.id, action="create", summary=f"Completed KRA run {run.id}", after=run)
    session.commit()
    session.refresh(run)
    return run


def kra_runtime_status() -> dict:
    settings = get_settings()
    return {
        "provider": settings.kra_llm_provider,
        "model": settings.kra_model or "deterministic-local",
        "api_key_configured": bool(settings.kra_api_key),
        "mcp_mode": settings.kra_mcp_mode,
        "ai_enabled": llm_enabled(),
    }
