from __future__ import annotations

import re
from urllib.parse import quote_plus

from sqlmodel import Session, select

from app.audit import compact_snapshot, log_event
from app.models import (
    AuditEvent,
    BusinessUnit,
    BuyerPortalInstance,
    Customer,
    CustomerWatchProfile,
    PortalInformationConnector,
    ProcurementPlatform,
    ProcurementSource,
)
from app.rule_loader import load_rule_file


def slugify_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return key or "organisation"


def list_public_sector_templates() -> list[dict]:
    return sorted(load_rule_file("public_sector_templates.yml").get("templates") or [], key=lambda item: item["name"])


def get_public_sector_template(template_key: str) -> dict:
    templates = {item["key"]: item for item in list_public_sector_templates()}
    if template_key not in templates:
        raise ValueError(f"Unknown public-sector template '{template_key}'.")
    return templates[template_key]


def list_preconfigured_customer_packs() -> list[dict]:
    return sorted(load_rule_file("customer_packs.yml").get("packs") or [], key=lambda item: item["display_name"])


def get_preconfigured_customer_pack(pack_key: str) -> dict:
    packs = {item["key"]: item for item in list_preconfigured_customer_packs()}
    if pack_key not in packs:
        raise ValueError(f"Unknown customer pack '{pack_key}'.")
    return _normalise_pack(packs[pack_key])


def build_discovery_pack(organisation_name: str, template_key: str, business_unit_name: str = "") -> dict:
    name = organisation_name.strip()
    if not name:
        raise ValueError("Organisation name is required.")
    template = get_public_sector_template(template_key)
    org_key = slugify_key(name)
    encoded = quote_plus(name)
    bu_name = business_unit_name.strip() or template.get("business_unit_hint") or "Core"
    aliases = [name]
    keywords = _unique_list([name, *template.get("watch_keywords", []), *template.get("domain_terms", [])])
    cpv_codes = template.get("cpv_codes", [])
    source_label = name.replace("'", "")
    pack = {
        "key": f"discovery_{org_key}",
        "display_name": f"{name} discovery pack",
        "description": f"Semi-configured public-source watch pack for {name} using the {template['name']} template.",
        "template_key": template_key,
        "business_unit": {
            "name": bu_name,
            "parent": "",
            "description": f"{template['name']} customer intelligence, opportunity monitoring and source-change tracking.",
        },
        "customer": {
            "name": name,
            "sector": template.get("sector", "Public sector"),
            "domain": "; ".join(template.get("domain_terms", [])),
            "customer_type": template.get("customer_type", "public body"),
            "region": template.get("region", "UK"),
            "aliases": aliases,
            "buying_entities": [name],
            "strategic_notes": [
                f"Generated from the {template['name']} Intelligence Pack template.",
                "Public-source watch profile created automatically; private portal registration and account-specific facts require human confirmation.",
            ],
        },
        "watch_profile": {
            "name": f"{name} watch",
            "keywords": keywords,
            "cpv_codes": cpv_codes,
            "domains": template.get("domain_terms", []),
        },
        "sources": [
            {
                "key": f"find_a_tender_{org_key}",
                "name": f"Find a Tender - {source_label}",
                "source_family": "official_notice",
                "source_type": "search_reference",
                "base_url": "https://www.find-tender.service.gov.uk",
                "query_url": f"https://www.find-tender.service.gov.uk/Search/Results?Keywords={encoded}",
                "official": True,
                "active": False,
                "coverage": f"UK public procurement notices mentioning {name}.",
                "auth_model": "none",
                "data_format": "HTML / OCDS links",
                "connector_status": "reference_only",
                "review_frequency": "daily",
                "notes": "Auto-generated reference search URL for human drill-through. Automated live retrieval uses official broad OCDS APIs and DIP customer filtering to avoid search-page rate limits.",
            },
            {
                "key": f"contracts_finder_{org_key}",
                "name": f"Contracts Finder - {source_label}",
                "source_family": "official_notice",
                "source_type": "search_reference",
                "base_url": "https://www.contractsfinder.service.gov.uk",
                "query_url": f"https://www.contractsfinder.service.gov.uk/Search/Results?Keywords={encoded}",
                "official": True,
                "active": False,
                "coverage": f"UK below-threshold, future and award notices mentioning {name}.",
                "auth_model": "none",
                "data_format": "HTML / OCDS links",
                "connector_status": "reference_only",
                "review_frequency": "daily",
                "notes": "Auto-generated reference search URL for human drill-through. Automated live retrieval uses official broad OCDS APIs and DIP customer filtering to avoid search-page rate limits.",
            },
        ],
        "portals": [],
        "connectors": [],
        "kra_queries": [
            {
                "agent": "Official Source Scout",
                "query": f"{name} {' '.join(template.get('watch_keywords', [])[:8])}",
            },
            {
                "agent": "Customer Memory Curator",
                "query": f"{name} supplier requirements procurement framework portal {' '.join(template.get('domain_terms', [])[:6])}",
            },
        ],
        "missing_actions": [
            "Confirm the organisation's official supplier or procurement pages.",
            "Confirm the active buyer portal family and supplier registration status.",
            "Confirm internal account owner and permitted document retrieval process.",
            *template.get("missing_private_fields", []),
        ],
        "template": template,
    }
    return _normalise_pack(pack)


def pack_summary_counts(pack: dict) -> dict[str, int]:
    return {
        "sources": len(pack.get("sources") or []),
        "portals": len(pack.get("portals") or []),
        "connectors": len(pack.get("connectors") or []),
        "watch_terms": len((pack.get("watch_profile") or {}).get("keywords") or []),
        "missing_actions": len(pack.get("missing_actions") or []),
    }


def apply_intelligence_pack(session: Session, pack: dict, actor: str = "local-user") -> dict:
    normalised = _normalise_pack(pack)
    result = {"created": [], "updated": [], "skipped": [], "warnings": [], "ids": {}}

    unit = _ensure_business_unit(session, normalised.get("business_unit") or {}, result)
    customer = _ensure_customer(session, normalised.get("customer") or {}, unit, result)
    watch_profile = _ensure_watch_profile(session, normalised.get("watch_profile") or {}, customer, unit, result)

    source_ids: list[int] = []
    for source_data in normalised.get("sources") or []:
        source = _ensure_source(session, source_data, result)
        if source.id:
            source_ids.append(source.id)

    portal_by_name: dict[str, BuyerPortalInstance] = {}
    for portal_data in normalised.get("portals") or []:
        portal = _ensure_portal(session, portal_data, customer, unit, result)
        portal_by_name[portal.portal_name] = portal

    connector_ids: list[int] = []
    for connector_data in normalised.get("connectors") or []:
        connector = _ensure_connector(session, connector_data, portal_by_name, result)
        if connector.id:
            connector_ids.append(connector.id)

    session.flush()
    result["ids"] = {
        "business_unit_id": unit.id if unit else None,
        "customer_id": customer.id if customer else None,
        "watch_profile_id": watch_profile.id if watch_profile else None,
        "source_ids": source_ids,
        "connector_ids": connector_ids,
    }
    event = AuditEvent(
        actor=actor,
        entity_type="IntelligencePack",
        entity_id=customer.id if customer else None,
        action="apply",
        summary=f"Applied intelligence pack {normalised.get('display_name')}",
        before_json="",
        after_json=compact_snapshot(
            {
                "pack_key": normalised.get("key"),
                "customer": (normalised.get("customer") or {}).get("name"),
                "created": result["created"],
                "updated": result["updated"],
                "skipped": result["skipped"],
                "warnings": result["warnings"],
            }
        ),
    )
    session.add(event)
    session.commit()
    return result


def _normalise_pack(pack: dict) -> dict:
    normalised = dict(pack)
    customer = dict(normalised.get("customer") or {})
    customer["aliases"] = _unique_list(customer.get("aliases") or [])
    customer["buying_entities"] = _unique_list(customer.get("buying_entities") or [])
    customer["strategic_notes"] = _unique_list(customer.get("strategic_notes") or [])
    normalised["customer"] = customer
    watch = dict(normalised.get("watch_profile") or {})
    watch["keywords"] = _unique_list(watch.get("keywords") or [])
    watch["cpv_codes"] = _unique_list(watch.get("cpv_codes") or [])
    watch["domains"] = _unique_list(watch.get("domains") or [])
    normalised["watch_profile"] = watch
    normalised["sources"] = [dict(item) for item in normalised.get("sources") or []]
    normalised["portals"] = [dict(item) for item in normalised.get("portals") or []]
    normalised["connectors"] = [dict(item) for item in normalised.get("connectors") or []]
    normalised["kra_queries"] = [dict(item) for item in normalised.get("kra_queries") or []]
    normalised["missing_actions"] = _unique_list(normalised.get("missing_actions") or [])
    normalised["summary_counts"] = pack_summary_counts(normalised)
    return normalised


def _ensure_business_unit(session: Session, data: dict, result: dict) -> BusinessUnit | None:
    name = (data.get("name") or "").strip()
    if not name:
        result["warnings"].append("No business unit name was supplied.")
        return None
    parent_id = None
    parent_name = (data.get("parent") or "").strip()
    if parent_name:
        parent = session.exec(select(BusinessUnit).where(BusinessUnit.name == parent_name)).first()
        if not parent:
            parent = BusinessUnit(name=parent_name, description=f"Parent unit for {name} account intelligence.")
            session.add(parent)
            session.flush()
            result["created"].append(f"Business unit: {parent.name}")
        parent_id = parent.id
    unit = session.exec(select(BusinessUnit).where(BusinessUnit.name == name)).first()
    if not unit:
        unit = BusinessUnit(name=name, parent_id=parent_id, description=data.get("description", ""))
        session.add(unit)
        session.flush()
        result["created"].append(f"Business unit: {unit.name}")
        return unit
    before = compact_snapshot(unit)
    changed = False
    if parent_id and unit.parent_id != parent_id:
        unit.parent_id = parent_id
        changed = True
    if data.get("description") and not unit.description:
        unit.description = data["description"]
        changed = True
    if changed:
        session.add(unit)
        log_event(session, entity_type="BusinessUnit", entity_id=unit.id, action="update", summary=f"Updated business unit from pack: {unit.name}", before=before, after=unit)
        result["updated"].append(f"Business unit: {unit.name}")
    else:
        result["skipped"].append(f"Business unit already configured: {unit.name}")
    return unit


def _ensure_customer(session: Session, data: dict, unit: BusinessUnit | None, result: dict) -> Customer | None:
    name = (data.get("name") or "").strip()
    if not name:
        result["warnings"].append("No customer name was supplied.")
        return None
    aliases = _unique_list(data.get("aliases") or [])
    customer = _find_customer(session, name, aliases)
    buying_entities = _join_values(data.get("buying_entities") or [])
    strategic_notes = _join_values(data.get("strategic_notes") or [])
    alias_text = _join_values(aliases)
    if not customer:
        customer = Customer(
            customer_name=name,
            business_unit_id=unit.id if unit else None,
            sector=data.get("sector", "Public sector"),
            domain=data.get("domain", ""),
            customer_type=data.get("customer_type", "public body"),
            region=data.get("region", "UK"),
            buying_entities=buying_entities,
            aliases=alias_text,
            strategic_notes=strategic_notes,
        )
        session.add(customer)
        session.flush()
        result["created"].append(f"Customer: {customer.customer_name}")
        return customer
    before = compact_snapshot(customer)
    changed = False
    fields = {
        "business_unit_id": unit.id if unit else customer.business_unit_id,
        "sector": data.get("sector", customer.sector),
        "domain": data.get("domain", customer.domain),
        "customer_type": data.get("customer_type", customer.customer_type),
        "region": data.get("region", customer.region),
    }
    for field_name, value in fields.items():
        if value and not getattr(customer, field_name):
            setattr(customer, field_name, value)
            changed = True
    merged_aliases = _merge_text_values(customer.aliases, aliases)
    merged_entities = _merge_text_values(customer.buying_entities, data.get("buying_entities") or [])
    merged_notes = _merge_text_values(customer.strategic_notes, data.get("strategic_notes") or [])
    for field_name, value in {"aliases": merged_aliases, "buying_entities": merged_entities, "strategic_notes": merged_notes}.items():
        if value != getattr(customer, field_name):
            setattr(customer, field_name, value)
            changed = True
    if unit and customer.business_unit_id is None:
        customer.business_unit_id = unit.id
        changed = True
    if changed:
        session.add(customer)
        session.flush()
        log_event(session, entity_type="Customer", entity_id=customer.id, action="update", summary=f"Updated customer from pack: {customer.customer_name}", before=before, after=customer)
        result["updated"].append(f"Customer: {customer.customer_name}")
    else:
        result["skipped"].append(f"Customer already configured: {customer.customer_name}")
    return customer


def _ensure_watch_profile(session: Session, data: dict, customer: Customer | None, unit: BusinessUnit | None, result: dict) -> CustomerWatchProfile | None:
    if not customer:
        return None
    name = data.get("name") or f"{customer.customer_name} watch"
    profile = session.exec(select(CustomerWatchProfile).where(CustomerWatchProfile.profile_name == name)).first()
    if not profile:
        profile = CustomerWatchProfile(
            profile_name=name,
            customer_id=customer.id,
            business_unit_id=unit.id if unit else customer.business_unit_id,
            buyer_aliases=customer.aliases,
            keywords=_join_values(data.get("keywords") or []),
            cpv_codes=_join_values(data.get("cpv_codes") or []),
            domains=_join_values(data.get("domains") or []),
            review_notes="Created by Intelligence Pack. Review and tune watch terms before relying on reports.",
        )
        session.add(profile)
        session.flush()
        result["created"].append(f"Watch profile: {profile.profile_name}")
        return profile
    before = compact_snapshot(profile)
    changed = False
    merged_fields = {
        "buyer_aliases": _split_values(customer.aliases),
        "keywords": data.get("keywords") or [],
        "cpv_codes": data.get("cpv_codes") or [],
        "domains": data.get("domains") or [],
    }
    for field_name, values in merged_fields.items():
        merged = _merge_text_values(getattr(profile, field_name), values)
        if merged != getattr(profile, field_name):
            setattr(profile, field_name, merged)
            changed = True
    if customer.id and profile.customer_id != customer.id:
        profile.customer_id = customer.id
        changed = True
    if unit and profile.business_unit_id != unit.id:
        profile.business_unit_id = unit.id
        changed = True
    if changed:
        session.add(profile)
        log_event(session, entity_type="CustomerWatchProfile", entity_id=profile.id, action="update", summary=f"Updated watch profile from pack: {profile.profile_name}", before=before, after=profile)
        result["updated"].append(f"Watch profile: {profile.profile_name}")
    else:
        result["skipped"].append(f"Watch profile already configured: {profile.profile_name}")
    return profile


def _ensure_source(session: Session, data: dict, result: dict) -> ProcurementSource:
    key = data.get("key", "")
    source = None
    if key:
        source = session.exec(select(ProcurementSource).where(ProcurementSource.source_key == key)).first()
    if not source:
        source = session.exec(select(ProcurementSource).where(ProcurementSource.name == data["name"])).first()
    if not source:
        source = ProcurementSource(
            source_key=key,
            name=data["name"],
            source_family=data.get("source_family", "official_notice"),
            source_type=data.get("source_type", "web_page"),
            base_url=data["base_url"],
            query_url=data["query_url"],
            official=bool(data.get("official", True)),
            active=bool(data.get("active", True)),
            coverage=data.get("coverage", ""),
            auth_model=data.get("auth_model", "none"),
            data_format=data.get("data_format", ""),
            connector_status=data.get("connector_status", "configured"),
            review_frequency=data.get("review_frequency", "manual"),
            notes=data.get("notes", ""),
        )
        session.add(source)
        session.flush()
        result["created"].append(f"Source: {source.name}")
    else:
        before = compact_snapshot(source)
        changed = False
        updates = {
            "source_key": key or source.source_key,
            "source_family": data.get("source_family", source.source_family),
            "source_type": data.get("source_type", source.source_type),
            "base_url": data.get("base_url", source.base_url),
            "query_url": data.get("query_url", source.query_url),
            "official": bool(data.get("official", source.official)),
            "active": bool(data.get("active", source.active)),
            "coverage": data.get("coverage", source.coverage),
            "auth_model": data.get("auth_model", source.auth_model),
            "data_format": data.get("data_format", source.data_format),
            "connector_status": data.get("connector_status", source.connector_status),
            "review_frequency": data.get("review_frequency", source.review_frequency),
            "notes": data.get("notes", source.notes),
        }
        for field_name, value in updates.items():
            if getattr(source, field_name) != value:
                setattr(source, field_name, value)
                changed = True
        if changed:
            session.add(source)
            log_event(session, entity_type="ProcurementSource", entity_id=source.id, action="update", summary=f"Updated source from pack: {source.name}", before=before, after=source)
            result["updated"].append(f"Source: {source.name}")
        else:
            result["skipped"].append(f"Source already configured: {source.name}")
    return source


def _ensure_platform(session: Session, data: dict, result: dict) -> ProcurementPlatform | None:
    name = (data.get("platform_name") or "").strip()
    if not name:
        return None
    platform = session.exec(select(ProcurementPlatform).where(ProcurementPlatform.name == name)).first()
    if platform:
        return platform
    platform = ProcurementPlatform(
        name=name,
        platform_type=data.get("platform_type", "buyer_portal"),
        login_model="public_api" if data.get("document_retrieval_mode") == "public_api_no_key" else "supplier_account",
        supported_actions="retrieve_metadata; detect_changes",
        requires_credentials=data.get("document_retrieval_mode") != "public_api_no_key",
        human_approval_required=True,
        connector_status="configured",
        notes="Created by Intelligence Pack. Confirm provider permissions before automated retrieval.",
    )
    session.add(platform)
    session.flush()
    result["created"].append(f"Platform: {platform.name}")
    return platform


def _ensure_portal(session: Session, data: dict, customer: Customer | None, unit: BusinessUnit | None, result: dict) -> BuyerPortalInstance:
    name = data["name"]
    portal = session.exec(select(BuyerPortalInstance).where(BuyerPortalInstance.portal_name == name)).first()
    platform = _ensure_platform(session, data, result)
    if not portal:
        portal = BuyerPortalInstance(
            portal_name=name,
            platform_id=platform.id if platform else None,
            customer_id=customer.id if customer else None,
            business_unit_id=unit.id if unit else None,
            portal_url=data.get("portal_url", ""),
            account_reference=data.get("account_reference", ""),
            access_status=data.get("access_status", "unknown"),
            document_retrieval_mode=data.get("document_retrieval_mode", "account_required_manual"),
            notes=data.get("notes", ""),
        )
        session.add(portal)
        session.flush()
        result["created"].append(f"Portal: {portal.portal_name}")
        return portal
    before = compact_snapshot(portal)
    changed = False
    updates = {
        "platform_id": platform.id if platform else portal.platform_id,
        "customer_id": customer.id if customer else portal.customer_id,
        "business_unit_id": unit.id if unit else portal.business_unit_id,
        "portal_url": data.get("portal_url", portal.portal_url),
        "document_retrieval_mode": data.get("document_retrieval_mode", portal.document_retrieval_mode),
    }
    for field_name, value in updates.items():
        if value and not getattr(portal, field_name):
            setattr(portal, field_name, value)
            changed = True
    merged_notes = _merge_text_values(portal.notes, [data.get("notes", "")])
    if merged_notes != portal.notes:
        portal.notes = merged_notes
        changed = True
    if changed:
        session.add(portal)
        log_event(session, entity_type="BuyerPortalInstance", entity_id=portal.id, action="update", summary=f"Updated portal from pack: {portal.portal_name}", before=before, after=portal)
        result["updated"].append(f"Portal: {portal.portal_name}")
    else:
        result["skipped"].append(f"Portal already configured: {portal.portal_name}")
    return portal


def _ensure_connector(session: Session, data: dict, portal_by_name: dict[str, BuyerPortalInstance], result: dict) -> PortalInformationConnector:
    name = data["name"]
    connector = session.exec(select(PortalInformationConnector).where(PortalInformationConnector.connector_name == name)).first()
    portal = portal_by_name.get(data.get("portal_name", ""))
    if not connector:
        connector = PortalInformationConnector(
            connector_name=name,
            portal_instance_id=portal.id if portal else None,
            integration_method=data.get("integration_method", "manual_assisted"),
            endpoint_url=data.get("endpoint_url", ""),
            auth_type=data.get("auth_type", "none"),
            enabled=bool(data.get("enabled", False)),
            read_only=True,
            allowed_operations=data.get("allowed_operations", "retrieve_metadata; retrieve_documents; detect_changes"),
            notes=data.get("notes", ""),
        )
        session.add(connector)
        session.flush()
        result["created"].append(f"Connector: {connector.connector_name}")
        return connector
    before = compact_snapshot(connector)
    portal_id = portal.id if portal else connector.portal_instance_id
    updates = {
        "portal_instance_id": portal_id,
        "integration_method": data.get("integration_method", connector.integration_method),
        "endpoint_url": data.get("endpoint_url", connector.endpoint_url),
        "auth_type": data.get("auth_type", connector.auth_type),
        "enabled": bool(data.get("enabled", connector.enabled)),
        "read_only": True,
        "allowed_operations": data.get("allowed_operations", connector.allowed_operations),
        "notes": data.get("notes", connector.notes),
    }
    changed = False
    for field_name, value in updates.items():
        if getattr(connector, field_name) != value:
            setattr(connector, field_name, value)
            changed = True
    if changed:
        session.add(connector)
        log_event(session, entity_type="PortalInformationConnector", entity_id=connector.id, action="update", summary=f"Updated connector from pack: {connector.connector_name}", before=before, after=connector)
        result["updated"].append(f"Connector: {connector.connector_name}")
    else:
        result["skipped"].append(f"Connector already configured: {connector.connector_name}")
    return connector


def _find_customer(session: Session, name: str, aliases: list[str]) -> Customer | None:
    customer = session.exec(select(Customer).where(Customer.customer_name == name)).first()
    if customer:
        return customer
    alias_candidates = {item.lower() for item in aliases if item}
    for item in session.exec(select(Customer)):
        existing_aliases = {value.lower() for value in _split_values(item.aliases)}
        if item.customer_name.lower() in alias_candidates or existing_aliases.intersection(alias_candidates):
            return item
    return None


def _split_values(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[;\n]+", value) if item.strip()]


def _join_values(values: list[str]) -> str:
    return "; ".join(_unique_list(values))


def _merge_text_values(existing: str, incoming: list[str]) -> str:
    return _join_values([*_split_values(existing), *incoming])


def _unique_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            unique.append(text)
    return unique
