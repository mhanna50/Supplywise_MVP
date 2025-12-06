"""Helpers for deriving financial signals from the SEC EDGAR APIs."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

SEC_COMPANY_SEARCH_URL = os.getenv('SEC_COMPANY_SEARCH_URL', 'https://data.sec.gov/search/company').rstrip('/')
SEC_COMPANY_FACTS_URL = os.getenv('SEC_COMPANY_FACTS_URL', 'https://data.sec.gov/api/xbrl/companyfacts').rstrip('/')
_DEFAULT_CONTACT = os.getenv('SEC_API_CONTACT_EMAIL', 'contact@supplywise.local')
SEC_USER_AGENT = os.getenv('SEC_API_USER_AGENT', f'SupplyWise/1.0 ({_DEFAULT_CONTACT})')


def _sec_headers() -> Dict[str, str]:
    return {
        'User-Agent': SEC_USER_AGENT,
        'Accept': 'application/json',
    }


def _safe_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _parse_date(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S%z'):
        try:
            return datetime.strptime(value[:len(fmt)], fmt)
        except ValueError:
            continue
    return None


def _recent_numeric_values(concept: Optional[Dict[str, Any]], limit: int = 4) -> List[Dict[str, Any]]:
    if not concept or not isinstance(concept, dict):
        return []

    units = concept.get('units') or {}
    records: List[Dict[str, Any]] = []
    for values in units.values():
        if not isinstance(values, list):
            continue
        for row in values:
            val = _safe_float(row.get('val'))
            if val is None:
                continue
            date = _parse_date(row.get('end') or row.get('fy'))
            sort_key = date or datetime.min
            records.append(
                {
                    'val': val,
                    'date': sort_key.date().isoformat() if date else (row.get('end') or None),
                    'end': row.get('end'),
                    '_sort': sort_key,
                },
            )

    records.sort(key=lambda item: item['_sort'], reverse=True)
    trimmed = records[:limit]
    for record in trimmed:
        record.pop('_sort', None)
    return trimmed


def _determine_trend(values: List[Dict[str, Any]]) -> str:
    if len(values) < 2:
        return 'unknown'
    latest, previous = values[0]['val'], values[1]['val']
    if previous == 0:
        if latest == 0:
            return 'stable'
        return 'increasing'
    change = (latest - previous) / abs(previous)
    if change > 0.05:
        return 'increasing'
    if change < -0.05:
        return 'decreasing'
    return 'stable'


def _choose_concept(facts: Dict[str, Any], names: List[str]) -> Optional[Dict[str, Any]]:
    for name in names:
        concept = facts.get(name)
        if concept:
            return concept
    return None


def _calculate_liquidity_risk(current_assets: Optional[float], current_liabilities: Optional[float]) -> str:
    if current_assets is None or current_liabilities is None or current_liabilities == 0:
        return 'unknown'

    ratio = current_assets / current_liabilities
    if ratio >= 2:
        return 'low'
    if ratio >= 1:
        return 'medium'
    return 'high'


def _summarize_facts(facts: Dict[str, Any]) -> Dict[str, Any]:
    gaap = (facts.get('facts') or {}).get('us-gaap') or {}

    revenue_concept = _choose_concept(
        gaap,
        [
            'Revenues',
            'SalesRevenueNet',
            'RevenueFromContractWithCustomerExcludingAssessedTax',
        ],
    )
    net_income_concept = _choose_concept(
        gaap,
        [
            'NetIncomeLoss',
            'ProfitLoss',
        ],
    )
    assets_concept = gaap.get('AssetsCurrent')
    liabilities_concept = gaap.get('LiabilitiesCurrent')
    going_concern_concept = _choose_concept(
        gaap,
        [
            'GoingConcern',
            'DisclosureOfGoingConcern',
            'GoingConcernPeriod',
        ],
    )

    revenue_values = _recent_numeric_values(revenue_concept)
    net_income_values = _recent_numeric_values(net_income_concept)
    assets_values = _recent_numeric_values(assets_concept, limit=1)
    liabilities_values = _recent_numeric_values(liabilities_concept, limit=1)
    current_assets = assets_values[0]['val'] if assets_values else None
    current_liabilities = liabilities_values[0]['val'] if liabilities_values else None
    liquidity_risk = _calculate_liquidity_risk(current_assets, current_liabilities)

    going_concern_flag = False
    going_values = _recent_numeric_values(going_concern_concept, limit=1)
    if going_values:
        going_concern_flag = bool(going_values[0]['val'] and going_values[0]['val'] > 0)

    key_indicators = {
        'revenue_trend': _determine_trend(revenue_values),
        'net_income_trend': _determine_trend(net_income_values),
        'liquidity_risk': liquidity_risk,
        'going_concern_flag': going_concern_flag,
    }

    has_data = any(
        value not in {'unknown', None}
        for key, value in key_indicators.items()
        if key != 'going_concern_flag'
    ) or going_concern_flag

    raw_snippet = {
        'revenue_values': revenue_values[:2],
        'net_income_values': net_income_values[:2],
        'assets': assets_values,
        'liabilities': liabilities_values,
    }

    return {
        'key_indicators': key_indicators,
        'raw_snippet': raw_snippet,
        'has_data': has_data,
    }


def _lookup_company(
    supplier_name: str,
    city: Optional[str],
    state: Optional[str],
    country: Optional[str],
) -> Optional[Dict[str, Any]]:
    params = {
        'keys': supplier_name,
        'start': 0,
    }
    if state:
        params['state'] = state
    if country:
        params['country'] = country

    try:
        response = requests.get(SEC_COMPANY_SEARCH_URL, params=params, headers=_sec_headers(), timeout=10)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.exception('SEC company search failed')
        raise RuntimeError(f'SEC company search failed: {exc}') from exc
    except ValueError as exc:
        logger.exception('SEC company search returned invalid JSON')
        raise RuntimeError(f'SEC company search returned invalid JSON: {exc}') from exc

    hits = (payload.get('hits') or {}).get('hits') or payload.get('results') or []
    for hit in hits:
        source = hit.get('_source') if isinstance(hit, dict) else hit
        if not isinstance(source, dict):
            continue
        cik = source.get('cik') or source.get('CIK') or source.get('cikNumber')
        if cik:
            return {
                'cik': str(cik).lstrip('0'),
                'ticker': source.get('ticker'),
                'company_name': source.get('entityName') or source.get('companyName'),
                'matching_city': city,
                'matching_state': state,
            }
    return None


def _fetch_company_facts(cik: str) -> Dict[str, Any]:
    cik_padded = str(cik).zfill(10)
    url = f"{SEC_COMPANY_FACTS_URL}/CIK{cik_padded}.json"
    try:
        response = requests.get(url, headers=_sec_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.exception('SEC company facts request failed for CIK %s', cik)
        raise RuntimeError(f'SEC company facts request failed: {exc}') from exc
    except ValueError as exc:
        logger.exception('SEC company facts returned invalid JSON for CIK %s', cik)
        raise RuntimeError(f'SEC company facts returned invalid JSON: {exc}') from exc


def get_financial_health_from_edgar(
    supplier_name: str,
    city: str | None,
    state: str | None,
    country: str | None,
    lei: str | None = None,
) -> Dict[str, Any]:
    """
    Use SEC EDGAR APIs to derive a financial health summary for a supplier.
    - If possible, map supplier to a public company via name (and optionally LEI / CIK if known).
    - If no public match is found, return {"available": False, "reason": "..."}.
    Return a dict shaped like:
    {
        "available": bool,
        "reason": str | None,
        "company_name": str | None,
        "ticker": str | None,
        "cik": str | None,
        "key_indicators": {
            "revenue_trend": "increasing|stable|decreasing|unknown",
            "net_income_trend": "increasing|stable|decreasing|unknown",
            "liquidity_risk": "low|medium|high|unknown",
            "going_concern_flag": bool
        },
        "raw": {...}  # trimmed raw snippet from EDGAR for debugging
    }
    """

    base_response = {
        'available': False,
        'reason': None,
        'company_name': None,
        'ticker': None,
        'cik': None,
        'key_indicators': {
            'revenue_trend': 'unknown',
            'net_income_trend': 'unknown',
            'liquidity_risk': 'unknown',
            'going_concern_flag': False,
        },
        'raw': {},
    }

    supplier_name = (supplier_name or '').strip()
    if not supplier_name:
        base_response['reason'] = 'Supplier name is required for SEC EDGAR lookup.'
        return base_response

    try:
        company_match = _lookup_company(supplier_name, city, state, country)
    except RuntimeError as exc:
        base_response['reason'] = str(exc)
        return base_response

    if not company_match:
        base_response['reason'] = f'No SEC filings matched "{supplier_name}".'
        return base_response

    base_response.update(
        {
            'company_name': company_match.get('company_name'),
            'ticker': company_match.get('ticker'),
            'cik': company_match.get('cik'),
        },
    )

    try:
        facts = _fetch_company_facts(company_match['cik'])
    except RuntimeError as exc:
        base_response['reason'] = str(exc)
        return base_response

    summary = _summarize_facts(facts)
    base_response['key_indicators'] = summary['key_indicators']
    base_response['raw'] = {
        'match': company_match,
        'facts_sample': summary['raw_snippet'],
    }
    base_response['available'] = summary['has_data']
    if not summary['has_data']:
        base_response['reason'] = 'SEC EDGAR did not expose enough financial facts for this supplier.'

    return base_response
