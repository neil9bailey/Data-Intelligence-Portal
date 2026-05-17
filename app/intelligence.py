from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from html import unescape
import json
import re
from urllib.parse import quote_plus, urljoin, urlparse

import httpx
from sqlmodel import Session, col, select

from app.audit import compact_snapshot, log_event
from app.models import (
    BusinessUnit,
    Customer,
    CustomerWatchProfile,
    DocumentRetrievalTask,
    ExtractedQualityQuestion,
    ExtractedRequirement,
    KRAAgentProfile,
    KRAFinding,
    KRAResearchRun,
    Opportunity,
    OpportunityDocument,
    ProcurementSource,
    SourceCheckSnapshot,
)
from app.rule_loader import load_rule_file
from app.settings import get_settings


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
    return source.query_url.replace("{query}", quote_plus(query))


def fetch_source_url(url: str) -> FetchResult:
    if not source_allowed(url):
        return FetchResult(False, 0, url, "", error="Blocked by approved-source allow-list.")
    try:
        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            response = client.get(url, headers={"User-Agent": "Data Intelligence Portal KRA local agent"})
        final_url = str(response.url)
        if not source_allowed(final_url):
            return FetchResult(False, response.status_code, final_url, "", error="Redirected outside approved domains.")
        return FetchResult(
            response.status_code < 400,
            response.status_code,
            final_url,
            response.text or "",
            response.headers.get("content-type", ""),
            "" if response.status_code < 400 else f"HTTP {response.status_code}",
        )
    except httpx.HTTPError as exc:
        return FetchResult(False, 0, url, "", error=f"Source check failed: {exc}")


def detect_schema(text: str, content_type: str = "") -> str:
    sample = (text or "")[:5000].lower()
    if "json" in content_type.lower() or "releases" in sample or "compiledrelease" in sample:
        return "ocds_json"
    if "xml" in content_type.lower() or "eforms" in sample:
        return "eforms_or_xml"
    if "<html" in sample or "<a " in sample:
        return "html"
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
        detected_schema=detect_schema(fetch.text, fetch.content_type),
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


def candidate_from_release(release: dict, source: ProcurementSource) -> CandidateOpportunity | None:
    tender = release.get("tender") if isinstance(release.get("tender"), dict) else {}
    planning = release.get("planning") if isinstance(release.get("planning"), dict) else {}
    buyer = release.get("buyer") if isinstance(release.get("buyer"), dict) else {}
    value = tender.get("value") if isinstance(tender.get("value"), dict) else {}
    tender_period = tender.get("tenderPeriod") if isinstance(tender.get("tenderPeriod"), dict) else {}
    title = textish(tender.get("title") or planning.get("rationale") or release.get("id") or release.get("ocid"))
    if not title:
        return None
    summary = textish(tender.get("description") or planning.get("rationale") or "")
    identifier = textish(release.get("id") or release.get("ocid") or title)
    links = release.get("links") if isinstance(release.get("links"), dict) else {}
    tags = release.get("tag") if isinstance(release.get("tag"), list) else []
    cpv: list[str] = []
    for item in tender.get("items") or []:
        if not isinstance(item, dict):
            continue
        classification = item.get("classification") if isinstance(item.get("classification"), dict) else {}
        label = " - ".join(part for part in [textish(classification.get("id")), textish(classification.get("description"))] if part)
        if label:
            cpv.append(label)
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
        source_url=textish(links.get("self") or release.get("url") or source.base_url),
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
    return terms or ["transport", "technology", "framework"]


def relevance_for_candidate(candidate: CandidateOpportunity, terms: list[str]) -> tuple[float, str]:
    combined = " ".join([candidate.title, candidate.buyer_name, candidate.summary, candidate.cpv_codes]).lower()
    matched = [term for term in terms if term and term in combined]
    if not matched:
        return 0, "No watch terms matched."
    return float(min(100, 20 + len(matched) * 12)), f"Matched terms: {', '.join(matched[:8])}."


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
    if candidate.notice_identifier:
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
    opportunity.customer_id = customer_id
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
    return opportunity, created


def requirement_themes_for_text(text: str) -> list[str]:
    lower = f" {text.lower()} "
    themes: list[str] = []
    for theme, patterns in (extraction_rules().get("themes") or {}).items():
        if any(str(pattern).lower() in lower for pattern in patterns):
            themes.append(str(theme))
    return themes


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
        requirement = ExtractedRequirement(
            opportunity_id=opportunity.id,
            customer_id=opportunity.customer_id,
            requirement_theme=theme,
            requirement_text=source_text[:1200],
            requirement_source=opportunity.source_url,
            confidence="medium",
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
        question = ExtractedQualityQuestion(
            opportunity_id=opportunity.id or 0,
            document_id=document.id,
            section_reference=document.document_type,
            question_text=question_text,
            weighting=weighting,
            requirement_theme=themes[0] if themes else "bid quality response",
            confidence="medium" if weighting else "low",
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
    url = source_query_url(source, ["transport", "technology", "framework"])
    fetch = fetcher(url)
    before = compact_snapshot(source)
    source.last_checked_at = datetime.now(UTC)
    source.last_status = f"HTTP {fetch.status_code}" if fetch.ok else (fetch.error or "failed")
    source.connector_status = "checked" if fetch.ok else "warning"
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
    customer_id: int | None = None,
    query: str = "",
    fetcher=fetch_source_url,
) -> KRAResearchRun:
    agent = session.get(KRAAgentProfile, agent_profile_id) if agent_profile_id else session.exec(select(KRAAgentProfile)).first()
    customer = session.get(Customer, customer_id) if customer_id else None
    sources = [session.get(ProcurementSource, source_id)] if source_id else list(session.exec(select(ProcurementSource).where(ProcurementSource.active == True)))  # noqa: E712
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
    terms = split_terms(query) + watch_profile_terms(session, customer=customer)
    findings_created = 0
    for source in sources:
        run.sources_checked += 1
        url = source_query_url(source, terms)
        fetch = fetcher(url)
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
        if fetch.ok:
            candidates = parse_ocds_candidates(fetch.text, source)
            if not candidates:
                candidates = parse_web_candidates(fetch.text, source, terms)
            for candidate in candidates[:20]:
                relevance, rationale = relevance_for_candidate(candidate, terms)
                if relevance <= 0:
                    continue
                opportunity, _ = upsert_opportunity(
                    session,
                    source,
                    candidate,
                    relevance,
                    rationale,
                    customer_id=customer_id,
                    business_unit_id=customer.business_unit_id if customer else None,
                )
                create_requirements_for_opportunity(session, opportunity, textish(f"{candidate.title}. {candidate.summary}. {candidate.cpv_codes}"))
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
    }
