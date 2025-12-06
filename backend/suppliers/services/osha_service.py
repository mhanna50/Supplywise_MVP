"""OSHA enforcement data helpers."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

OSHA_API_BASE_URL = os.getenv('OSHA_API_BASE_URL', 'https://enforcedata.dol.gov/services/osha/inspection').rstrip('/')


def _extract_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get('data'), list):
        return payload['data']
    results = payload.get('Results') or payload.get('results')
    if isinstance(results, dict):
        for key in ('data', 'Records', 'Inspection', 'rows'):
            value = results.get(key)
            if isinstance(value, list):
                return value
    if isinstance(results, list):
        return results
    return []


def _parse_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _parse_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _collect_date(record: Dict[str, Any]) -> Optional[str]:
    for key in ('close_conf_date', 'closeConfDate', 'openingDate', 'open_date', 'inspection_date'):
        value = record.get(key)
        if value:
            try:
                # Standardize to YYYY-MM-DD for presentation.
                parsed = datetime.fromisoformat(value.replace('Z', ''))
                return parsed.date().isoformat()
            except ValueError:
                for fmt in ('%m/%d/%Y', '%Y%m%d'):
                    try:
                        parsed = datetime.strptime(value, fmt)
                        return parsed.date().isoformat()
                    except ValueError:
                        continue
    return None


def _count_violations(record: Dict[str, Any]) -> int:
    for key in (
        'total_current_violations',
        'totalCurrentViolations',
        'serious_violations',
        'seriousViolations',
        'total_violations',
    ):
        if key in record:
            return _parse_int(record.get(key))
    return 0


def _extract_penalty(record: Dict[str, Any]) -> float:
    for key in (
        'total_penalty',
        'totalPenalty',
        'total_current_penalty',
        'totalCurrentPenalty',
        'initial_penalty',
        'penalty',
    ):
        if key in record:
            return _parse_float(record.get(key))
    return 0.0


def _risk_indicator(inspections: int, violations: int, penalties: float) -> str:
    if inspections == 0:
        return 'unknown'
    violation_rate = violations / max(inspections, 1)
    if violation_rate >= 1 or penalties > 100000:
        return 'high'
    if violation_rate >= 0.3 or penalties > 10000:
        return 'medium'
    return 'low'


def get_compliance_from_osha(supplier_name: str, city: str | None, state: str | None) -> Dict[str, Any]:
    """
    Use OSHA enforcement/inspection open data APIs to gather safety/compliance signals.
    Match by establishment name + state (+ city if available).
    Return a dict like:
    {
        "available": bool,
        "reason": str | None,
        "inspections_count": int,
        "violations_count": int,
        "total_penalties_usd": float,
        "last_inspection_date": str | None,
        "risk_indicator": "low|medium|high|unknown",
        "raw": {...}  # trimmed sample record(s)
    }
    """

    base_response = {
        'available': False,
        'reason': None,
        'inspections_count': 0,
        'violations_count': 0,
        'total_penalties_usd': 0.0,
        'last_inspection_date': None,
        'risk_indicator': 'unknown',
        'raw': {},
    }

    supplier_name = (supplier_name or '').strip()
    if not supplier_name or not state:
        base_response['reason'] = 'Supplier name and state are required for OSHA lookup.'
        return base_response

    params: Dict[str, Any] = {
        'establishment': supplier_name,
        'state': state,
        '$top': 200,
    }
    if city:
        params['city'] = city

    try:
        response = requests.get(OSHA_API_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.exception('OSHA enforcement request failed')
        base_response['reason'] = f'OSHA enforcement request failed: {exc}'
        return base_response
    except ValueError as exc:
        logger.exception('OSHA enforcement returned invalid JSON')
        base_response['reason'] = f'OSHA enforcement returned invalid JSON: {exc}'
        return base_response

    records = _extract_records(payload)
    if not records:
        base_response['reason'] = 'No OSHA inspections matched this supplier.'
        return base_response

    penalties = sum(_extract_penalty(record) for record in records)
    violations = sum(_count_violations(record) for record in records)
    last_dates = filter(None, (_collect_date(record) for record in records))
    last_inspection_date = max(last_dates, default=None)

    base_response.update(
        {
            'available': True,
            'reason': None,
            'inspections_count': len(records),
            'violations_count': violations,
            'total_penalties_usd': round(penalties, 2),
            'last_inspection_date': last_inspection_date,
            'risk_indicator': _risk_indicator(len(records), violations, penalties),
            'raw': {'sample_records': records[:5]},
        },
    )
    return base_response
