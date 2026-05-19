from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class BusinessUnit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="businessunit.id")
    description: str = ""
    active: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_name: str = Field(index=True)
    business_unit_id: Optional[int] = Field(default=None, foreign_key="businessunit.id")
    sector: str = "Public sector"
    domain: str = "transport"
    customer_type: str = "public body"
    region: str = "UK"
    buying_entities: str = ""
    aliases: str = ""
    strategic_notes: str = ""
    portal_notes: str = ""
    active: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class CustomerWatchProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    profile_name: str = Field(index=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    business_unit_id: Optional[int] = Field(default=None, foreign_key="businessunit.id")
    buyer_aliases: str = ""
    keywords: str = ""
    cpv_codes: str = ""
    domains: str = ""
    minimum_value: float = 0
    active: bool = True
    review_notes: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class ProcurementSource(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    source_key: str = Field(default="", index=True)
    source_family: str = "official_notice"
    source_type: str = "ocds_api"
    base_url: str
    query_url: str
    official: bool = True
    active: bool = True
    coverage: str = ""
    auth_model: str = "none"
    data_format: str = ""
    dedupe_strategy: str = "ocid_or_reference"
    review_frequency: str = "manual"
    change_tracking_enabled: bool = True
    requires_human_approval: bool = False
    connector_status: str = "configured"
    last_checked_at: Optional[datetime] = None
    last_status: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class SourceCheckSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: Optional[int] = Field(default=None, foreign_key="procurementsource.id", index=True)
    checked_at: datetime = Field(default_factory=utc_now, index=True)
    query_url: str = ""
    ok: bool = False
    status_code: int = 0
    content_hash: str = Field(default="", index=True)
    previous_hash: str = ""
    change_type: str = "unknown"
    detected_schema: str = ""
    connector_status: str = ""
    notes: str = ""


class NewsFeedSource(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    source_key: str = Field(default="", index=True)
    feed_url: str
    publisher: str = ""
    theme: str = ""
    official: bool = True
    active: bool = True
    refresh_frequency: str = "manual"
    last_checked_at: Optional[datetime] = None
    last_status: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class NewsFeedItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    feed_source_id: Optional[int] = Field(default=None, foreign_key="newsfeedsource.id", index=True)
    title: str = Field(index=True)
    link: str = Field(default="", index=True)
    summary: str = ""
    published_at: Optional[datetime] = Field(default=None, index=True)
    content_hash: str = Field(default="", index=True)
    review_status: str = "new"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ProcurementPlatform(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    platform_type: str = "buyer_portal"
    login_model: str = "supplier_account"
    supported_actions: str = ""
    requires_credentials: bool = True
    human_approval_required: bool = True
    active: bool = True
    connector_status: str = "manual_assisted"
    platform_domains: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class BuyerPortalInstance(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    portal_name: str = Field(index=True)
    platform_id: Optional[int] = Field(default=None, foreign_key="procurementplatform.id")
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    business_unit_id: Optional[int] = Field(default=None, foreign_key="businessunit.id")
    portal_url: str = ""
    account_reference: str = ""
    access_status: str = "unknown"
    document_retrieval_mode: str = "account_required_manual"
    notes: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class PortalInformationConnector(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    connector_name: str = Field(index=True)
    portal_instance_id: Optional[int] = Field(default=None, foreign_key="buyerportalinstance.id", index=True)
    integration_method: str = "manual_assisted"
    endpoint_url: str = ""
    auth_type: str = "none"
    api_key_secret_name: str = ""
    api_key_header_name: str = "X-API-Key"
    api_key_query_name: str = "api_key"
    default_opportunity_id: Optional[int] = Field(default=None, foreign_key="opportunity.id")
    enabled: bool = False
    read_only: bool = True
    allowed_operations: str = "retrieve_metadata; retrieve_documents; detect_changes"
    last_checked_at: Optional[datetime] = None
    last_status: str = "not_checked"
    last_http_status: int = 0
    notes: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class PortalRetrievalRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    connector_id: Optional[int] = Field(default=None, foreign_key="portalinformationconnector.id", index=True)
    portal_instance_id: Optional[int] = Field(default=None, foreign_key="buyerportalinstance.id")
    opportunity_id: Optional[int] = Field(default=None, foreign_key="opportunity.id")
    started_at: datetime = Field(default_factory=utc_now, index=True)
    finished_at: Optional[datetime] = None
    status: str = "started"
    http_status: int = 0
    content_hash: str = Field(default="", index=True)
    items_found: int = 0
    documents_created: int = 0
    findings_created: int = 0
    error_summary: str = ""
    guardrail_summary: str = "Read-only information retrieval only. No portal login, expressions of interest or submissions are automated."


class Opportunity(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: Optional[int] = Field(default=None, foreign_key="procurementsource.id")
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    business_unit_id: Optional[int] = Field(default=None, foreign_key="businessunit.id")
    title: str = Field(index=True)
    buyer_name: str = ""
    notice_identifier: str = Field(default="", index=True)
    ocid: str = ""
    notice_type: str = ""
    procurement_stage: str = ""
    published_date: Optional[date] = None
    deadline_date: Optional[date] = None
    value_low: float = 0
    value_high: float = 0
    currency: str = "GBP"
    cpv_codes: str = ""
    location: str = ""
    source_url: str = ""
    summary: str = ""
    status: str = "new"
    relevance_score: float = 0
    relevance_rationale: str = ""
    content_hash: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class OpportunityMatchEvidence(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: Optional[int] = Field(default=None, foreign_key="opportunity.id", index=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    business_unit_id: Optional[int] = Field(default=None, foreign_key="businessunit.id")
    evidence_type: str = "matched"
    matched_term: str = ""
    source_field: str = ""
    score_delta: float = 0
    rationale: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class OpportunityFeedback(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: Optional[int] = Field(default=None, foreign_key="opportunity.id", index=True)
    reviewer: str = "local-user"
    feedback_type: str = "other"
    notes: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class OpportunityDocument(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunity.id")
    title: str
    document_type: str = "notice"
    url_or_path: str = ""
    source_hash: str = ""
    retrieval_status: str = "linked"
    human_review_status: str = "pending"
    platform_name: str = ""
    content_summary: str = ""
    storage_provider: str = "none"
    document_storage_ref: str = ""
    classification_label: str = ""
    retention_status: str = "standard"
    reviewed_by: str = ""
    reviewed_at: Optional[datetime] = None
    source_access_notes: str = ""
    extracted_at: datetime = Field(default_factory=utc_now)
    notes: str = ""


class DocumentRetrievalTask(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: Optional[int] = Field(default=None, foreign_key="opportunity.id", index=True)
    portal_instance_id: Optional[int] = Field(default=None, foreign_key="buyerportalinstance.id")
    task_name: str = "Manual portal document retrieval"
    status: str = "requested"
    owner: str = "local-user"
    due_date: Optional[date] = None
    guardrail_summary: str = "Manual retrieval only. No credentials are stored and no portal action is automated."
    notes: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class ExtractedRequirement(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: Optional[int] = Field(default=None, foreign_key="opportunity.id", index=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    requirement_theme: str = Field(index=True)
    requirement_category: str = Field(default="general", index=True)
    requirement_text: str
    requirement_source: str = ""
    confidence: str = "medium"
    confidence_reason: str = ""
    human_review_status: str = "pending"
    created_at: datetime = Field(default_factory=utc_now)


class ExtractedQualityQuestion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunity.id", index=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    document_id: Optional[int] = Field(default=None, foreign_key="opportunitydocument.id")
    section_reference: str = ""
    question_text: str
    weighting: str = ""
    requirement_theme: str = ""
    requirement_category: str = Field(default="general", index=True)
    confidence: str = "medium"
    confidence_reason: str = ""
    human_review_status: str = "pending"
    created_at: datetime = Field(default_factory=utc_now)


class KRAAgentProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    role: str
    mcp_toolkit: str = ""
    allowed_actions: str = ""
    guardrails: str = ""
    active: bool = True
    notes: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class KRAResearchRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    agent_profile_id: Optional[int] = Field(default=None, foreign_key="kraagentprofile.id")
    source_id: Optional[int] = Field(default=None, foreign_key="procurementsource.id")
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    opportunity_id: Optional[int] = Field(default=None, foreign_key="opportunity.id")
    run_type: str = "manual"
    status: str = "started"
    query: str = ""
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
    sources_checked: int = 0
    findings_created: int = 0
    guardrail_summary: str = ""
    error_summary: str = ""


class KRAFinding(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: Optional[int] = Field(default=None, foreign_key="kraresearchrun.id", index=True)
    source_id: Optional[int] = Field(default=None, foreign_key="procurementsource.id")
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    opportunity_id: Optional[int] = Field(default=None, foreign_key="opportunity.id")
    finding_type: str = "source_observation"
    title: str
    summary: str = ""
    source_url: str = ""
    content_hash: str = ""
    confidence: str = "medium"
    change_status: str = "new"
    human_review_status: str = "pending"
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    system_prompt_hash: str = ""
    user_prompt_hash: str = ""
    source_context_hash: str = ""
    output_hash: str = ""
    reviewed_by: str = ""
    reviewed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)


class IntelligenceReport(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    report_name: str = Field(index=True)
    report_type: str = "executive_summary"
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    business_unit_id: Optional[int] = Field(default=None, foreign_key="businessunit.id")
    generated_at: datetime = Field(default_factory=utc_now)
    generated_by: str = "local-user"
    markdown: str = ""


class EmailConfiguration(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    profile_name: str = Field(default="Default local profile", index=True)
    delivery_mode: str = "file_outbox"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password_secret_name: str = ""
    smtp_password: str = ""
    use_tls: bool = True
    sender_name: str = "Contracted Opportunity Finder"
    sender_email: str = "no-reply@local.test"
    default_recipients: str = ""
    enabled: bool = False
    notes: str = ""
    updated_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)


class EmailDeliveryLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    report_id: Optional[int] = Field(default=None, foreign_key="intelligencereport.id")
    delivery_mode: str = "file_outbox"
    sender: str = ""
    recipients: str = ""
    subject: str = ""
    status: str = "created"
    attachment_format: str = "md"
    outbox_path: str = ""
    error: str = ""


class DigestProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    report_type: str = "executive_summary"
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    business_unit_id: Optional[int] = Field(default=None, foreign_key="businessunit.id")
    recipients: str = ""
    frequency_label: str = "manual"
    enabled: bool = True
    export_format: str = "pdf"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ClientInterestSignal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: Optional[int] = Field(default=None, foreign_key="opportunity.id", index=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    contact_name: str = ""
    contact_email: str = ""
    signal: str = "interested"
    notes: str = ""
    status: str = "new"
    created_at: datetime = Field(default_factory=utc_now)


class AutomationRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    finished_at: Optional[datetime] = None
    actor: str = "local-user"
    run_type: str = "admin_full_cycle"
    status: str = "started"
    report_id: Optional[int] = Field(default=None, foreign_key="intelligencereport.id")
    summary: str = ""
    steps_json: str = ""
    stored_report_path: str = ""
    email_log_id: Optional[int] = Field(default=None, foreign_key="emaildeliverylog.id")


class AuditEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    actor: str = "local-user"
    entity_type: str = Field(index=True)
    entity_id: Optional[int] = Field(default=None, index=True)
    action: str = Field(index=True)
    summary: str = ""
    before_json: str = ""
    after_json: str = ""
