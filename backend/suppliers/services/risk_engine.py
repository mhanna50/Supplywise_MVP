"""Toy risk engine used to turn supplier signals into a numeric score."""

from __future__ import annotations

from typing import Any, Dict, Optional


def _clamp(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, round(value)))


def compute_risk_score(azure_data: Optional[Dict[str, Any]], gleif_data: Dict[str, Any]) -> Dict[str, Any]:
    """Return an overall risk score, highlight factors, and surface debug info.

    Scoring heuristic (higher score == lower risk):
    * Start from 50.
    * +20 if there is an associated GLEIF record.
    * +10 if the Azure confidence score is >= 0.9, +5 if >= 0.7.
    * -10 if Azure confidence score is below 0.4.
    * +15 if the GLEIF registration is listed as active, otherwise -15.
    * Small boost if both Azure and GLEIF countries exist and match.
    """

    score = 50.0
    factors: Dict[str, Any] = {}

    azure_result = azure_data or {}
    gleif_entity = gleif_data.get('enriched_entity') if gleif_data else None

    has_gleif = gleif_entity is not None
    factors['has_gleif_record'] = has_gleif
    score += 20 if has_gleif else -10

    azure_confidence = azure_result.get('score')
    factors['azure_confidence'] = azure_confidence

    if isinstance(azure_confidence, (int, float)):
        if azure_confidence >= 0.9:
            score += 10
        elif azure_confidence >= 0.7:
            score += 5
        elif azure_confidence < 0.4:
            score -= 10

    registration_status = gleif_entity.get('registration_status') if gleif_entity else None
    factors['gleif_registration_status'] = registration_status

    if registration_status:
        if registration_status.lower() in {'issued', 'lapsed', 'retired'}:
            # treat "issued" as active, while other states reduce confidence
            score += 15 if registration_status.lower() == 'issued' else -15
    if not registration_status and gleif_entity:
        score -= 5

    azure_country = azure_result.get('country')
    gleif_country = None
    if gleif_entity:
        legal_address = gleif_entity.get('legal_address') or {}
        gleif_country = legal_address.get('country') or legal_address.get('countryCode')

    factors['country_alignment'] = azure_country == gleif_country if gleif_country else None

    if azure_country and gleif_country:
        if azure_country == gleif_country:
            score += 5
        else:
            score -= 5

    debug_payload = {
        'azure_inputs': azure_result,
        'gleif_inputs': gleif_entity,
        'intermediate_score': score,
    }

    overall = _clamp(score)

    return {
        'overall_score': overall,
        'factors': factors,
        'debug_payload': debug_payload,
    }
