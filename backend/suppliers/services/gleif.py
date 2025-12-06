"""Integration logic for retrieving GLEIF enrichment data."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

GLEIF_RECORDS_URL = os.getenv('GLEIF_BASE_URL', 'https://api.gleif.org/api/v1/lei-records').rstrip('/')
GLEIF_HEADERS = {'Accept': 'application/vnd.api+json'}


def _simplify_gleif_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Pluck the most relevant fields from a GLEIF record."""
    attributes = record.get('attributes', {})
    entity = attributes.get('entity', {})
    registration = attributes.get('registration', {})

    return {
        'lei': record.get('id'),
        'legal_name': entity.get('legalName', {}).get('name'),
        'legal_address': entity.get('legalAddress'),
        'registered_at': registration.get('initialRegistrationDate'),
        'registration_status': registration.get('status'),
        'entity_status': entity.get('status'),
        'next_renewal_date': registration.get('nextRenewalDate'),
        'raw': record,
    }


def _build_pretty_gleif_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    """Convert the first GLEIF record into a simplified entity summary."""

    attributes = record.get('attributes') or {}
    entity = attributes.get('entity') or {}
    registration = attributes.get('registration') or {}
    legal_address = entity.get('legalAddress') or {}

    def _first_line(address: Dict[str, Any]) -> Optional[str]:
        return (
            address.get('line1')
            or address.get('firstAddressLine')
            or address.get('addressLine1')
        )

    return {
        'lei': attributes.get('lei') or record.get('id'),
        'legal_name': (entity.get('legalName') or {}).get('name'),
        'registration_status': registration.get('status'),
        'entity_status': entity.get('status'),
        'legal_jurisdiction': entity.get('legalJurisdiction'),
        'legal_address': {
            'line1': _first_line(legal_address),
            'city': legal_address.get('city'),
            'postal_code': legal_address.get('postalCode'),
            'country': legal_address.get('country'),
        },
    }


def _gleif_request_metadata(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Return debugging metadata for the outbound GLEIF request."""

    try:
        prepared = requests.Request('GET', endpoint, params=params).prepare()
        url = prepared.url
    except Exception:  # pragma: no cover - extremely rare
        url = f"{endpoint}?{params}"

    return {
        'method': 'GET',
        'url': url,
        'params': params,
    }


def _build_legal_name_params(name: str) -> Dict[str, Any]:
    return {
        'filter[entity.legalName]': (name or '').strip(),
        'page[size]': 5,
    }


def _call_lei_records(params: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    request_meta = _gleif_request_metadata(GLEIF_RECORDS_URL, params.copy())
    response = requests.get(GLEIF_RECORDS_URL, params=params, headers=GLEIF_HEADERS, timeout=10)
    response.raise_for_status()
    payload = response.json()
    return payload, request_meta


def gleif_deep_lookup_from_azure_result(azure_poi: Dict[str, Any]) -> Dict[str, Any]:
    """Deeply enrich an Azure Maps POI by finding its GLEIF counterpart.

    Given a single Azure Maps business result, leverage its identifying
    details to search the GLEIF API and return both the raw response and a
    prettified summary. The returned dict always contains ``gleif_raw``,
    ``gleif_pretty``, and ``error`` keys as described in the spec.
    """

    if not isinstance(azure_poi, dict):
        azure_poi = {}

    poi = azure_poi.get('poi') or {}
    if not isinstance(poi, dict):
        poi = {}

    name = (poi.get('name') or azure_poi.get('name') or '').strip()
    params = _build_legal_name_params(name)
    if not params['filter[entity.legalName]']:
        return {
            'gleif_raw': None,
            'gleif_pretty': None,
            'error': 'GLEIF lookup requires a business name.',
        }

    try:
        records_payload, _ = _call_lei_records(params)
    except requests.RequestException as exc:
        logger.exception('GLEIF lookup failed')
        return {
            'gleif_raw': None,
            'gleif_pretty': None,
            'error': f'GLEIF lookup failed: {exc}',
        }
    except ValueError as exc:
        logger.exception('Invalid JSON from GLEIF')
        return {
            'gleif_raw': None,
            'gleif_pretty': None,
            'error': f'GLEIF lookup failed: {exc}',
        }

    records = records_payload.get('data') or []
    first_record = records[0] if records else None
    if not first_record:
        return {
            'gleif_raw': None,
            'gleif_pretty': None,
            'error': 'No matching GLEIF records were found.',
        }

    gleif_pretty = _build_pretty_gleif_summary(first_record)

    return {
        'gleif_raw': records_payload,
        'gleif_pretty': gleif_pretty,
        'error': None,
    }


def get_gleif_enrichment(name: str) -> Dict[str, Any]:
    """Fetch potential enrichment data from GLEIF using the legal name filter."""

    params = _build_legal_name_params(name)
    request_meta = _gleif_request_metadata(GLEIF_RECORDS_URL, params.copy())

    if not params['filter[entity.legalName]']:
        return {
            'raw_gleif_response': None,
            'enriched_entity': None,
            'error': 'GLEIF enrichment requires a business name.',
            'request_metadata': request_meta,
        }

    logger.info('Querying GLEIF records', extra={'endpoint': GLEIF_RECORDS_URL})

    try:
        data, request_meta = _call_lei_records(params)
    except requests.RequestException as exc:
        logger.exception('GLEIF enrichment failed')
        return {
            'raw_gleif_response': None,
            'enriched_entity': None,
            'error': str(exc),
            'request_metadata': request_meta,
        }
    except ValueError as exc:
        logger.exception('Invalid JSON from GLEIF')
        return {
            'raw_gleif_response': None,
            'enriched_entity': None,
            'error': str(exc),
            'request_metadata': request_meta,
        }

    records = data.get('data') or []
    first_record = records[0] if records else None
    enriched = _simplify_gleif_record(first_record) if first_record else None

    return {
        'raw_gleif_response': data,
        'enriched_entity': enriched,
        'request_metadata': request_meta,
    }
