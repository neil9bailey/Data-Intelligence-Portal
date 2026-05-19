from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable

from app.auth import CurrentUser
from app.models import ClientInterestSignal, IntelligenceReport, Opportunity
from app.settings import get_settings


@dataclass(frozen=True)
class AccessScope:
    customer_ids: tuple[int, ...] = ()
    business_unit_ids: tuple[int, ...] = ()
    restricted: bool = False


def _to_int_tuple(values: object) -> tuple[int, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        raw_values: Iterable[object] = [item.strip() for item in values.replace(";", ",").split(",")]
    elif isinstance(values, list | tuple | set):
        raw_values = values
    else:
        raw_values = [values]
    parsed: list[int] = []
    for value in raw_values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number not in parsed:
            parsed.append(number)
    return tuple(parsed)


def _scope_from_mapping(mapping: dict) -> AccessScope:
    return AccessScope(
        customer_ids=_to_int_tuple(mapping.get("customer_ids") or mapping.get("customers")),
        business_unit_ids=_to_int_tuple(mapping.get("business_unit_ids") or mapping.get("business_units")),
        restricted=True,
    )


def scope_for_user(user: CurrentUser) -> AccessScope:
    if user.can_admin or user.role == "auditor":
        return AccessScope()
    raw = get_settings().access_scopes_json.strip()
    if not raw:
        return AccessScope()
    try:
        config = json.loads(raw)
    except json.JSONDecodeError:
        return AccessScope()
    if not isinstance(config, dict):
        return AccessScope()

    lookup_keys = [user.username.lower(), *(f"group:{group.lower()}" for group in user.groups), "*"]
    for key in lookup_keys:
        value = config.get(key)
        if isinstance(value, dict):
            return _scope_from_mapping(value)
    return AccessScope()


def is_scope_restricted(user: CurrentUser) -> bool:
    return scope_for_user(user).restricted


def report_in_scope(report: IntelligenceReport, user: CurrentUser) -> bool:
    scope = scope_for_user(user)
    if not scope.restricted:
        return True
    if report.customer_id and report.customer_id in scope.customer_ids:
        return True
    return bool(report.business_unit_id and report.business_unit_id in scope.business_unit_ids)


def opportunity_in_scope(opportunity: Opportunity, user: CurrentUser) -> bool:
    scope = scope_for_user(user)
    if not scope.restricted:
        return True
    if opportunity.customer_id and opportunity.customer_id in scope.customer_ids:
        return True
    return bool(opportunity.business_unit_id and opportunity.business_unit_id in scope.business_unit_ids)


def interest_in_scope(signal: ClientInterestSignal, user: CurrentUser, opportunities_by_id: dict[int, Opportunity]) -> bool:
    scope = scope_for_user(user)
    if not scope.restricted:
        return True
    if signal.customer_id and signal.customer_id in scope.customer_ids:
        return True
    if signal.opportunity_id and signal.opportunity_id in opportunities_by_id:
        return opportunity_in_scope(opportunities_by_id[signal.opportunity_id], user)
    return False
