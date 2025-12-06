"""EPA ECHO facility search helpers for ESG profiling."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

EPA_ECHO_BASE_URL = os.getenv('EPA_ECHO_BASE_URL', 'https://echo.epa.gov/echo/rest/facility').rstrip('/')


def _parse_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
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


def _extract_facilities(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    results = payload.get('Results') or payload.get('results') or {}
    if isinstance(results, dict):
        for key in ('Facilities', 'Facility', 'rows', 'data'):
            value = results.get(key)
            if isinstance(value, list):
                return value
    if isinstance(results, list):
        return results
    return []


def _sum_field(records: List[Dict[str, Any]], keys: List[str]) -> float:
    total = 0.0
    for record in records:
        for key in keys:
            if key in record:
                try:
                    total += float(record[key])
                    break
                except (TypeError, ValueError):
                    continue
    return round(total, 2)


def _count_recent_violations(records: List[Dict[str, Any]]) -> int:
    total = 0
    for record in records:
        for key in ('QtrsWithNC', 'qtrs_with_nc', 'RecentViolationCount'):
            if key in record:
                try:
                    total += int(record[key])
                    break
                except (TypeError, ValueError):
                    continue
        else:
            flag = record.get('CurrVioFlag') or record.get('curr_vio_flag')
            if isinstance(flag, str) and flag.lower() == 'y':
                total += 1
            elif flag in (True, 1):
                total += 1
    return total


def _latest_violation_date(records: List[Dict[str, Any]]) -> Optional[str]:
    dates: List[str] = []
    for record in records:
        for key in ('LastViolationDate', 'last_violation_date', 'LastPenaltyDate', 'last_penalty_date'):
            normalized = _parse_date(record.get(key))
            if normalized:
                dates.append(normalized)
                break
    if not dates:
        return None
    return max(dates)


def _program_flag(record: Dict[str, Any], keys: List[str]) -> bool:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str):
            if value.strip().upper() in {'Y', 'YES', 'TRUE', 'T'}:
                return True
        elif isinstance(value, (bool, int)):
            if bool(value):
                return True
    return False


def _derive_program_flags(records: List[Dict[str, Any]]) -> Dict[str, bool]:
    flags = {'air': False, 'water': False, 'waste': False}
    for record in records:
        flags['air'] = flags['air'] or _program_flag(record, ['AIR_FLAG', 'AirFlag', 'air_flag'])
        flags['water'] = flags['water'] or _program_flag(record, ['CWA_FLAG', 'water_flag', 'WaterFlag'])
        flags['waste'] = flags['waste'] or _program_flag(record, ['RCRA_FLAG', 'WasteFlag', 'waste_flag'])
    return flags


def _esg_risk_indicator(violations: int, penalties: float) -> str:
    if violations >= 10 or penalties > 200000:
        return 'high'
    if violations >= 3 or penalties > 25000:
        return 'medium'
    if violations > 0 or penalties > 0:
        return 'low'
    return 'unknown'


def get_esg_from_epa_echo(
    supplier_name: str,
    city: str | None,
    state: str | None,
    postal_code: str | None = None,
) -> Dict[str, Any]:
    """
    Use EPA ECHO facility search APIs to derive environmental & ESG-related signals
    for the supplier's facility/facilities.
    Match by name + city + state (and postal_code when available).
    Return:
    {
        "available": bool,
        "reason": str | None,
        "facilities_found": int,
        "recent_violations": int,
        "total_penalties_usd": float,
        "last_violation_date": str | None,
        "program_flags": {
            "air": bool,
            "water": bool,
            "waste": bool
        },
        "esg_risk_indicator": "low|medium|high|unknown",
        "raw": {...}  # trimmed ECHO response
    }
    """

    base_response = {
        'available': False,
        'reason': None,
        'facilities_found': 0,
        'recent_violations': 0,
        'total_penalties_usd': 0.0,
        'last_violation_date': None,
        'program_flags': {'air': False, 'water': False, 'waste': False},
        'esg_risk_indicator': 'unknown',
        'raw': {},
    }

    supplier_name = (supplier_name or '').strip()
    if not supplier_name:
        base_response['reason'] = 'Supplier name is required for EPA ECHO lookup.'
        return base_response

    params: Dict[str, Any] = {
        'qname': supplier_name,
        'output': 'JSON',
        'pageno': 1,
        'pagesize': 100,
    }

    if city:
        params['qcity'] = city
    if state:
        params['qstate'] = state
    if postal_code:
        params['qzip'] = postal_code

    try:
        response = requests.get(EPA_ECHO_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.exception('EPA ECHO request failed')
        base_response['reason'] = f'EPA ECHO request failed: {exc}'
        return base_response
    except ValueError as exc:
        logger.exception('EPA ECHO returned invalid JSON')
        base_response['reason'] = f'EPA ECHO returned invalid JSON: {exc}'
        return base_response

    facilities = _extract_facilities(payload)
    if not facilities:
        base_response['reason'] = 'No EPA ECHO facilities matched the provided supplier details.'
        return base_response

    penalties = _sum_field(
        facilities,
        ['TotalPenalties', 'total_penalties', 'Penalties', 'totalPenalties'],
    )
    violations = _count_recent_violations(facilities)
    last_violation = _latest_violation_date(facilities)
    flags = _derive_program_flags(facilities)

    base_response.update(
        {
            'available': True,
            'reason': None,
            'facilities_found': len(facilities),
            'recent_violations': violations,
            'total_penalties_usd': penalties,
            'last_violation_date': last_violation,
            'program_flags': flags,
            'esg_risk_indicator': _esg_risk_indicator(violations, penalties),
            'raw': {'sample_facilities': facilities[:5]},
        },
    )
    return base_response
