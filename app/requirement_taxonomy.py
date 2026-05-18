from __future__ import annotations

from collections import Counter

from app.rule_loader import load_rule_file


DEFAULT_CATEGORY = "general"


def extraction_rules() -> dict:
    return load_rule_file("extraction.yml")


def requirement_categories() -> dict[str, list[str]]:
    configured = extraction_rules().get("requirement_categories") or {}
    categories: dict[str, list[str]] = {}
    for category, terms in configured.items():
        categories[str(category)] = [str(term).strip().lower() for term in terms or [] if str(term).strip()]
    return categories


def requirement_themes_for_text(text: str) -> list[str]:
    lower = f" {(text or '').lower()} "
    themes: list[str] = []
    for theme, patterns in (extraction_rules().get("themes") or {}).items():
        if any(str(pattern).lower() in lower for pattern in patterns):
            themes.append(str(theme))
    return themes


def classify_requirement_category(text: str, theme: str = "") -> str:
    haystack = f" {theme} {text} ".lower()
    categories = requirement_categories()
    best_category = DEFAULT_CATEGORY
    best_score = 0
    for category, terms in categories.items():
        score = sum(1 for term in terms if term and term in haystack)
        if score > best_score:
            best_category = category
            best_score = score
    return best_category


def assess_requirement_confidence(
    text: str,
    *,
    theme: str = "",
    category: str = "",
    customer_id: int | None = None,
    opportunity_id: int | None = None,
    source_reference: str = "",
    weighting: str = "",
) -> tuple[str, str]:
    rules = extraction_rules().get("confidence") or {}
    scoring = rules.get("scoring") or {}
    strong_terms = [str(term).lower() for term in rules.get("strong_text_terms") or []]
    haystack = f" {theme} {text} ".lower()
    score = 0
    reasons: list[str] = []

    if customer_id:
        score += int(scoring.get("linked_customer", 2))
        reasons.append("linked customer")
    if opportunity_id:
        score += int(scoring.get("linked_opportunity", 2))
        reasons.append("linked opportunity")
    if source_reference:
        score += int(scoring.get("source_reference", 1))
        reasons.append("source reference")
    if category and category != DEFAULT_CATEGORY:
        score += int(scoring.get("specific_category", 1))
        reasons.append(f"category {category.replace('_', ' ')}")
    if any(term in haystack for term in strong_terms):
        score += int(scoring.get("strong_text", 1))
        reasons.append("buyer requirement language")
    if weighting:
        score += int(scoring.get("weighting_present", 1))
        reasons.append("weighting detected")
    if len((text or "").strip()) >= 120:
        score += int(scoring.get("text_min_length", 1))
        reasons.append("substantive text")

    high_min = int(rules.get("high_min_score", 7))
    medium_min = int(rules.get("medium_min_score", 4))
    if score >= high_min:
        label = "high"
    elif score >= medium_min:
        label = "medium"
    else:
        label = "low"
    reason = f"Agent confidence {label}: score {score}; " + (", ".join(reasons) if reasons else "limited traceability")
    return label, reason


def category_trend_counts(items) -> Counter:
    return Counter((getattr(item, "requirement_category", "") or DEFAULT_CATEGORY) for item in items)
