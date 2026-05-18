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


def category_trend_counts(items) -> Counter:
    return Counter((getattr(item, "requirement_category", "") or DEFAULT_CATEGORY) for item in items)

