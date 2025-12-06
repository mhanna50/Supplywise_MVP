"""Aggregate helper for deep supplier risk profiling."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict

from .edgar_service import get_financial_health_from_edgar
from .epa_echo_service import get_esg_from_epa_echo
from .fema_service import get_operational_risk_from_fema
from .osha_service import get_compliance_from_osha

logger = logging.getLogger(__name__)


def _safe_attr(obj: Any, attr: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(attr)
    return getattr(obj, attr, None)


def run_deep_risk_enrichment(supplier: Any) -> Dict[str, Any]:
    """
    Given a Supplier model instance (or similar DTO) with at least:
      - name
      - address.city
      - address.state
      - address.postal_code
      - address.country
      - optional LEI, ticker, etc.
    call all external enrichment services and return a unified JSON structure.

    Return structure:
    {
        "financial_health": {...},      # EDGAR summary dict
        "compliance_legal": {...},      # OSHA + any compliance-related view of ECHO
        "operational_resilience": {...},# FEMA + relevant OSHA signals
        "esg_reputation": {...}         # EPA ECHO (ESG) and any ESG-related OSHA info
    }
    """

    name = _safe_attr(supplier, 'name')
    city = _safe_attr(supplier, 'city')
    state = _safe_attr(supplier, 'state')
    postal_code = _safe_attr(supplier, 'postal_code') or _safe_attr(supplier, 'postalCode')
    country = _safe_attr(supplier, 'country')
    lei = _safe_attr(supplier, 'lei')
    county = _safe_attr(supplier, 'county')

    def _wrap(callable_name: str, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception('Deep risk worker "%s" failed', callable_name)
            return {
                'available': False,
                'reason': f'{callable_name} failed: {exc}',
                'raw': {},
            }

    tasks = {
        'financial_health': lambda: get_financial_health_from_edgar(name, city, state, country, lei),
        'compliance_legal': lambda: get_compliance_from_osha(name, city, state),
        'operational_resilience': lambda: get_operational_risk_from_fema(city, state, county, postal_code),
        'esg_reputation': lambda: get_esg_from_epa_echo(name, city, state, postal_code),
    }

    results: Dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        future_map = {
            executor.submit(_wrap, key, task): key
            for key, task in tasks.items()
        }
        for future in as_completed(future_map):
            key = future_map[future]
            results[key] = future.result()

    return results
