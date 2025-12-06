"""Lightweight OpenAI helper used to generate explanatory text."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - library installed in runtime env
    OpenAI = None  # type: ignore

logger = logging.getLogger(__name__)


def _create_client() -> Any:
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key or OpenAI is None:
        logger.warning('OpenAI client not available or API key missing')
        return None
    return OpenAI(api_key=api_key)


def generate_risk_explanation(
    score: int,
    factors: Dict[str, Any],
    azure_summary: Dict[str, Any],
    gleif_summary: Dict[str, Any],
) -> str:
    """Call OpenAI and return a short justification paragraph."""

    model = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')
    client = _create_client()
    payload = {
        'score': score,
        'factors': factors,
        'azure_summary': azure_summary,
        'gleif_summary': gleif_summary,
    }

    prompt = (
        "You are a supplier risk analyst. Given the JSON payload below, "
        "write a concise 3-5 sentence explanation that justifies the risk "
        "score for a non-technical business audience. Focus on the most "
        "meaningful signals and keep the tone factual.\n\n"
        f"Payload: {json.dumps(payload, default=str)}"
    )

    if not client:
        return 'OpenAI client is not configured; unable to generate explanation.'

    try:
        response = client.responses.create(
            model=model,
            input=prompt,
        )
        first_output = response.output[0].content[0].text if response.output else None
        return first_output.strip() if first_output else 'Explanation unavailable.'
    except Exception as exc:  # pragma: no cover - runtime only
        logger.exception('OpenAI explanation request failed')
        return f'Explanation unavailable: {exc}'
