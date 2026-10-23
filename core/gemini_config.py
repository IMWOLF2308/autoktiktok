"""Shared Gemini defaults and conversion from display names to API model IDs."""
import re


DEFAULT_REVIEW_MODEL = "gemini-3.8-flash"
FALLBACK_REVIEW_MODEL = "gemini-3.5-flash-lite"


def normalize_review_model(model_name: str) -> str:
    name = model_name.strip()
    candidate = re.sub(r"[\s_]+", "-", name.lower()).removeprefix("models/")
    if re.fullmatch(r"gemini-[a-z0-9]+(?:[.-][a-z0-9]+)*", candidate):
        return candidate
    # Preserve custom resource IDs; never substitute a different model.
    return name
