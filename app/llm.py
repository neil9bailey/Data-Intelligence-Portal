from __future__ import annotations

import httpx

from app.settings import get_settings


class LLMError(RuntimeError):
    pass


def llm_enabled() -> bool:
    settings = get_settings()
    return settings.kra_llm_provider.lower() == "openai_direct" and bool(settings.kra_api_key) and bool(settings.kra_model)


def generate_llm_text(system_prompt: str, user_prompt: str, max_output_tokens: int = 700) -> str:
    settings = get_settings()
    if not llm_enabled():
        raise LLMError("KRA LLM provider is not configured.")
    payload = {
        "model": settings.kra_model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "max_output_tokens": max_output_tokens,
    }
    headers = {
        "Authorization": f"Bearer {settings.kra_api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post("https://api.openai.com/v1/responses", json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise LLMError(f"OpenAI request failed: {exc}") from exc
    if response.status_code >= 400:
        detail = response.text[:300].replace(settings.kra_api_key, "***redacted***")
        raise LLMError(f"OpenAI request returned HTTP {response.status_code}: {detail}")
    try:
        data = response.json()
    except ValueError as exc:
        raise LLMError("OpenAI response was not valid JSON.") from exc
    text = str(data.get("output_text") or "").strip()
    if text:
        return text
    parts: list[str] = []
    for item in data.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(str(content["text"]))
    text = "\n".join(parts).strip()
    if not text:
        raise LLMError("OpenAI response did not include text output.")
    return text


def kra_system_prompt() -> str:
    return (
        "You are the Data Intelligence Portal KRA research assistant. "
        "Summarise only the provided public-source and user-reviewed intelligence. "
        "Do not invent facts, do not make bid/no-bid decisions, do not claim compliance approval, "
        "and always mark conclusions as requiring human review."
    )
