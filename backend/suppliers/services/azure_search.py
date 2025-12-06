"""Integration helpers for Azure Maps fuzzy search."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

logger = logging.getLogger(__name__)


def _clean_category_set(raw: Optional[str]) -> Optional[str]:
    """Return a comma-separated list of numeric category IDs or None."""
    if not raw:
        return None

    sanitized = raw.split('#', 1)[0].strip()
    if not sanitized:
        return None

    digits_only = [part.strip() for part in sanitized.split(',') if part.strip().isdigit()]
    return ','.join(digits_only) or None


def _compose_query(
    query: Optional[str],
    industry: Optional[str],
    city: Optional[str],
    state: Optional[str],
    country: Optional[str],
) -> str:
    """Combine search terms and optional location hints for Azure fuzzy search."""

    base_terms = [value.strip() for value in [query, industry] if value and value.strip()]
    if not base_terms:
        raise ValueError('Azure Maps search query cannot be empty.')

    base_query = ' '.join(base_terms)
    location_parts = [value.strip() for value in [city, state, country] if value and value.strip()]

    if location_parts:
        return ', '.join([base_query] + location_parts)
    return base_query


def _redact_subscription_key(url: str) -> str:
    """Return the URL with any subscription-key query parameter removed."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url

    pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() == 'subscription-key':
            pairs.append((key, '[REDACTED]'))
        else:
            pairs.append((key, value))

    redacted_query = urlencode(pairs)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, redacted_query, parsed.fragment))


def _simplify_result(item: Dict[str, Any]) -> Dict[str, Any]:
    """Return a pared down structure that is easy for the frontend to render."""
    poi = item.get('poi', {})
    address = item.get('address', {})
    position = item.get('position', {})
    phone = poi.get('phone') or poi.get('phoneNumber')
    website = poi.get('url') or poi.get('website')

    return {
        'id': item.get('id') or poi.get('id'),
        'name': poi.get('name') or item.get('name'),
        'address': address.get('freeformAddress'),
        'country': address.get('countryCodeISO3') or address.get('countryCode'),
        'state': address.get('countrySubdivision'),
        'city': address.get('municipality') or address.get('localName'),
        'postalCode': address.get('postalCode'),
        'latitude': position.get('lat'),
        'longitude': position.get('lon'),
        'score': item.get('score'),
        'categories': poi.get('classifications') or [],
        'phone': phone,
        'website': website,
        'raw': item,
    }


def search_businesses(
    query: Optional[str],
    city: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None,
    *,
    industry: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Call Azure Maps fuzzy search and return simplified business results."""

    base_url = os.getenv('AZURE_MAPS_BASE_URL', 'https://atlas.microsoft.com').rstrip('/')
    api_version = os.getenv('AZURE_MAPS_SEARCH_API_VERSION', '1.0')
    subscription_key = os.getenv('AZURE_MAPS_SUBSCRIPTION_KEY')
    endpoint = f"{base_url}/search/fuzzy/json"

    if not subscription_key:
        logger.error('AZURE_MAPS_SUBSCRIPTION_KEY is not configured')
        return {
            'results': [],
            'raw_azure_response': None,
            'error': 'Azure Maps subscription key is not configured',
        }

    try:
        combined_query = _compose_query(query, industry, city, state, country)
    except ValueError as exc:
        return {
            'results': [],
            'raw_azure_response': None,
            'error': str(exc),
        }

    params: Dict[str, Any] = {
        'api-version': api_version,
        'subscription-key': subscription_key,
        'query': combined_query,
        'limit': limit,
    }

    category_set = _clean_category_set(os.getenv('AZURE_MAPS_CATEGORY_SET'))
    if category_set:
        # Provide valid numeric IDs (comma separated) to narrow results to specific industries.
        params['categorySet'] = category_set

    if country:
        params['countrySet'] = country

    logger.info('Searching Azure Maps fuzzy endpoint', extra={'endpoint': endpoint})

    request_params = params.copy()
    retry_without_categories = 'categorySet' in request_params

    while True:
        try:
            response = requests.get(endpoint, params=request_params, timeout=10)
        except requests.RequestException as exc:
            logger.exception('Azure Maps search request failed')
            return {
                'results': [],
                'raw_azure_response': None,
                'error': f'Azure Maps search request failed: {exc}',
            }

        if response.status_code == requests.codes.ok:
            break

        truncated_body = (response.text or '')[:500]
        logger.error(
            'Azure Maps search returned non-200',
            extra={
                'status_code': response.status_code,
                'url': _redact_subscription_key(response.url),
                'body': truncated_body,
            },
        )

        if (
            retry_without_categories
            and response.status_code == requests.codes.bad_request
            and 'categorySet' in request_params
        ):
            logger.warning('Retrying Azure Maps search without categorySet due to 400 response.')
            request_params.pop('categorySet', None)
            retry_without_categories = False
            continue

        return {
            'results': [],
            'raw_azure_response': None,
            'error': f'Azure Maps search failed with {response.status_code}: {truncated_body}',
        }

    try:
        data = response.json()
    except ValueError as exc:
        logger.exception('Azure Maps returned invalid JSON')
        return {
            'results': [],
            'raw_azure_response': None,
            'error': f'Azure Maps returned invalid JSON: {exc}',
        }

    simplified: List[Dict[str, Any]] = []
    for item in data.get('results', []):
        simple = _simplify_result(item)
        name = (simple.get('name') or '').strip()
        if not name:
            continue
        simplified.append(simple)

    return {
        'results': simplified,
        'raw_azure_response': data,
    }
