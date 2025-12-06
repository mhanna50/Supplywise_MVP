"""FEMA disaster-summary helpers for operational resilience scoring."""

from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

FEMA_API_BASE_URL = os.getenv(
    'FEMA_API_BASE_URL',
    'https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries',
).rstrip('/')


def _normalize_filter_value(value: str) -> str:
    return value.replace("'", "''")


def _risk_from_count(count: int) -> str:
    if count >= 10:
        return 'high'
    if count >= 4:
        return 'medium'
    if count > 0:
        return 'low'
    return 'unknown'


def _overall_risk(total_events: int) -> str:
    if total_events >= 20:
        return 'high'
    if total_events >= 8:
        return 'medium'
    if total_events > 0:
        return 'low'
    return 'unknown'


def _build_filter(state: str, county: Optional[str]) -> str:
    start_date = (datetime.utcnow() - timedelta(days=5 * 365)).strftime('%Y-%m-%d')
    clauses = [
        f"state eq '{_normalize_filter_value(state.upper())}'",
        f"incidentBeginDate ge '{start_date}T00:00:00Z'",
    ]
    if county:
        clauses.append(f"contains(declaredCountyArea,'{_normalize_filter_value(county)}')")
    return ' and '.join(clauses)


def _categorize_incidents(records: List[Dict[str, Any]]) -> Dict[str, str]:
    hazard_counts = Counter()
    for record in records:
        hazard = (record.get('incidentType') or '').strip().lower()
        if not hazard:
            continue
        hazard_counts[hazard] += 1

    flood_count = sum(
        hazard_counts[key]
        for key in hazard_counts
        if 'flood' in key
    )
    storm_count = sum(
        hazard_counts[key]
        for key in hazard_counts
        if any(word in key for word in ('storm', 'hurricane', 'tornado', 'typhoon'))
    )
    wildfire_count = sum(
        hazard_counts[key]
        for key in hazard_counts
        if 'fire' in key
    )

    return {
        'flood_risk': _risk_from_count(flood_count),
        'storm_risk': _risk_from_count(storm_count),
        'wildfire_risk': _risk_from_count(wildfire_count),
    }


def get_operational_risk_from_fema(
    city: str | None,
    state: str | None,
    county: str | None = None,
    postal_code: str | None = None,
) -> Dict[str, Any]:
    """
    Use FEMA (and/or NOAA) disaster/emergency-related APIs to approximate physical/operational disruption risk
    for the supplier location.
    Use city/state and postal code (if available) to determine the relevant county/region and query FEMA.
    Return:
    {
        "available": bool,
        "reason": str | None,
        "region": {
            "state": str | None,
            "county": str | None,
            "fips": str | None
        },
        "hazard_profile": {
            "flood_risk": "low|medium|high|unknown",
            "storm_risk": "low|medium|high|unknown",
            "wildfire_risk": "low|medium|high|unknown",
            "other_events_last_5_years": int
        },
        "overall_operational_disruption_risk": "low|medium|high|unknown",
        "raw": {...}  # trimmed FEMA response
    }
    """

    base_response = {
        'available': False,
        'reason': None,
        'region': {
            'state': state,
            'county': county,
            'fips': None,
        },
        'hazard_profile': {
            'flood_risk': 'unknown',
            'storm_risk': 'unknown',
            'wildfire_risk': 'unknown',
            'other_events_last_5_years': 0,
        },
        'overall_operational_disruption_risk': 'unknown',
        'raw': {},
    }

    if not state:
        base_response['reason'] = 'State or territory information is required for FEMA risk lookup.'
        return base_response

    params = {
        '$filter': _build_filter(state, county),
        '$orderby': 'incidentBeginDate desc',
        '$top': 1000,
    }

    try:
        response = requests.get(FEMA_API_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.exception('FEMA disaster summary request failed')
        base_response['reason'] = f'FEMA disaster summary request failed: {exc}'
        return base_response
    except ValueError as exc:
        logger.exception('FEMA disaster summary returned invalid JSON')
        base_response['reason'] = f'FEMA disaster summary returned invalid JSON: {exc}'
        return base_response

    records = payload.get('DisasterDeclarationsSummaries') or payload.get('DisasterDeclarations') or []
    if not records:
        base_response['reason'] = 'No FEMA disaster summaries matched the given region in the last 5 years.'
        return base_response

    hazard_profile = _categorize_incidents(records)
    hazard_profile['other_events_last_5_years'] = len(records)

    first = records[0]
    state_code = first.get('state') or state
    county_name = first.get('declaredCountyArea') or county
    fips_state = first.get('fipsStateCode')
    fips_county = first.get('fipsCountyCode')
    fips_code = None
    if fips_state and fips_county:
        fips_code = f"{fips_state}{fips_county}"

    base_response['region'] = {
        'state': state_code,
        'county': county_name,
        'fips': fips_code,
    }
    base_response['hazard_profile'] = hazard_profile
    base_response['overall_operational_disruption_risk'] = _overall_risk(len(records))
    base_response['available'] = True
    base_response['raw'] = {'sample_disasters': records[:5]}
    return base_response
