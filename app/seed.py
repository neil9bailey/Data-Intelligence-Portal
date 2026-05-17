from sqlmodel import Session, select

from app.models import (
    BusinessUnit,
    Customer,
    CustomerWatchProfile,
    NewsFeedSource,
    ProcurementPlatform,
    ProcurementSource,
    BuyerPortalInstance,
    Opportunity,
    OpportunityDocument,
    ExtractedRequirement,
    KRAAgentProfile,
)
from app.rule_loader import load_rule_file


def seed_sources(session: Session) -> None:
    existing = {source.source_key or source.name for source in session.exec(select(ProcurementSource))}
    for item in load_rule_file("sources.yml").get("sources") or []:
        if item["key"] in existing or item["name"] in existing:
            continue
        session.add(
            ProcurementSource(
                source_key=item["key"],
                name=item["name"],
                source_family=item.get("source_family", "official_notice"),
                source_type=item.get("source_type", "ocds_api"),
                base_url=item["base_url"],
                query_url=item["query_url"],
                official=bool(item.get("official", True)),
                active=bool(item.get("active", True)),
                coverage=item.get("coverage", ""),
                auth_model=item.get("auth_model", "none"),
                data_format=item.get("data_format", ""),
                dedupe_strategy=item.get("dedupe_strategy", "ocid_or_reference"),
                connector_status=item.get("connector_status", "configured"),
                notes=item.get("notes", ""),
            )
        )
    session.commit()


def seed_platforms(session: Session) -> None:
    existing = {platform.name for platform in session.exec(select(ProcurementPlatform))}
    for item in load_rule_file("platforms.yml").get("platforms") or []:
        if item["name"] in existing:
            continue
        session.add(
            ProcurementPlatform(
                name=item["name"],
                platform_type=item.get("platform_type", "buyer_portal"),
                login_model=item.get("login_model", "supplier_account"),
                supported_actions="; ".join(item.get("supported_actions") or []),
                requires_credentials=bool(item.get("requires_credentials", True)),
                human_approval_required=bool(item.get("human_approval_required", True)),
                active=bool(item.get("active", True)),
                connector_status=item.get("connector_status", "manual_assisted"),
                platform_domains=item.get("platform_domains", ""),
                notes=item.get("notes", ""),
            )
        )
    session.commit()


def seed_news_feeds(session: Session) -> None:
    existing = {feed.source_key or feed.name for feed in session.exec(select(NewsFeedSource))}
    for item in load_rule_file("news_feeds.yml").get("feeds") or []:
        if item["key"] in existing or item["name"] in existing:
            continue
        session.add(
            NewsFeedSource(
                source_key=item["key"],
                name=item["name"],
                feed_url=item["feed_url"],
                publisher=item.get("publisher", ""),
                theme=item.get("theme", ""),
                official=bool(item.get("official", True)),
                active=bool(item.get("active", True)),
                refresh_frequency=item.get("refresh_frequency", "manual"),
                notes=item.get("notes", ""),
            )
        )
    session.commit()


def seed_kra_agents(session: Session) -> None:
    existing = {agent.name for agent in session.exec(select(KRAAgentProfile))}
    for item in load_rule_file("kra_agents.yml").get("agents") or []:
        if item["name"] in existing:
            continue
        session.add(
            KRAAgentProfile(
                name=item["name"],
                role=item["role"],
                mcp_toolkit=item.get("mcp_toolkit", ""),
                allowed_actions=item.get("allowed_actions", ""),
                guardrails=item.get("guardrails", ""),
                active=bool(item.get("active", True)),
            )
        )
    session.commit()


def seed_reference_data(session: Session) -> None:
    seed_sources(session)
    seed_platforms(session)
    seed_kra_agents(session)
    seed_news_feeds(session)


def seed_demo_data(session: Session) -> None:
    seed_reference_data(session)
    if session.exec(select(Customer)).first():
        return
    transport = BusinessUnit(name="Transport", description="Transport-sector account and opportunity intelligence.")
    network = BusinessUnit(name="Network Services", description="Network services customer intelligence.")
    nuclear = BusinessUnit(name="Nuclear / HPC", description="Critical infrastructure and nuclear account intelligence.")
    session.add(transport)
    session.add(network)
    session.add(nuclear)
    session.commit()
    for unit in [transport, network, nuclear]:
        session.refresh(unit)
    customers = [
        Customer(
            customer_name="National Highways",
            business_unit_id=transport.id,
            sector="Public sector transport",
            domain="highways",
            customer_type="government-owned company",
            buying_entities="National Highways; Highways England",
            aliases="National Highways; NH; Highways England",
            strategic_notes="Roadside technology, operational resilience, asset management, network services and safety-critical operations.",
        ),
        Customer(
            customer_name="Transport for London",
            business_unit_id=transport.id,
            sector="Public sector transport",
            domain="multimodal transport",
            customer_type="transport authority",
            buying_entities="TfL; London Underground; Surface Transport",
            aliases="TfL; Transport for London",
            strategic_notes="Passenger data, operational systems, asset renewals, service reliability and cyber resilience.",
        ),
        Customer(
            customer_name="Hinkley Point C",
            business_unit_id=nuclear.id,
            sector="Critical infrastructure",
            domain="nuclear power",
            customer_type="private/public critical infrastructure",
            buying_entities="HPC; Hinkley Point C",
            aliases="HPC; Hinkley Point C",
            strategic_notes="Secure communications, operational technology and controlled document governance.",
        ),
    ]
    session.add_all(customers)
    session.commit()
    for customer in customers:
        session.refresh(customer)
        session.add(
            CustomerWatchProfile(
                profile_name=f"{customer.customer_name} watch",
                customer_id=customer.id,
                business_unit_id=customer.business_unit_id,
                buyer_aliases=customer.aliases,
                keywords="cyber, resilience, operational technology, data, service management, asset management",
                domains=customer.domain,
                active=True,
            )
        )
    procontract = session.exec(select(ProcurementPlatform).where(ProcurementPlatform.name == "ProContract")).first()
    if procontract:
        session.add(
            BuyerPortalInstance(
                portal_name="National Highways procurement portal",
                platform_id=procontract.id,
                customer_id=customers[0].id,
                business_unit_id=transport.id,
                portal_url="https://procontract.due-north.com/",
                access_status="registered",
                notes="Manual-assisted portal tracking only. No credentials stored.",
            )
        )
    source = session.exec(select(ProcurementSource).where(ProcurementSource.source_key == "find_a_tender")).first()
    opportunity = Opportunity(
        source_id=source.id if source else None,
        customer_id=customers[0].id,
        business_unit_id=transport.id,
        title="Roadside technology and operational resilience framework",
        buyer_name="National Highways",
        notice_identifier="demo-roadside-001",
        procurement_stage="early engagement",
        value_high=5000000,
        cpv_codes="72000000 - IT services; 50330000 - Communications equipment maintenance",
        source_url="https://www.find-tender.service.gov.uk/",
        summary="Framework signal covering roadside technology, SCADA, cyber security, service management, asset maintenance and operational resilience.",
        status="watching",
        relevance_score=88,
        relevance_rationale="Matched National Highways, roadside, operational technology, cyber and resilience terms.",
        content_hash="demo-roadside-001",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)
    document = OpportunityDocument(
        opportunity_id=opportunity.id,
        title="Demo ITT quality question extract",
        document_type="itt_extract",
        retrieval_status="review_required",
        platform_name="ProContract",
        content_summary="Quality questions mention low-latency operational technology, resilience and service management.",
        notes="Quality question 1: Describe your approach to resilient roadside operational technology service continuity. Weighting 20%",
    )
    session.add(document)
    session.add(
        ExtractedRequirement(
            opportunity_id=opportunity.id,
            customer_id=customers[0].id,
            requirement_theme="operational resilience",
            requirement_text=opportunity.summary,
            requirement_source=opportunity.source_url,
            confidence="high",
            human_review_status="pending",
        )
    )
    session.commit()
