"""API views for supplier search and risk assessment."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    BusinessInfoSerializer,
    SelectedAzureBusinessSerializer,
    SupplierAssessmentSerializer,
    SupplierDeepRiskSerializer,
    SupplierSearchSerializer,
)
from .services import (
    compute_risk_score,
    generate_risk_explanation,
    get_gleif_enrichment,
    gleif_deep_lookup_from_azure_result,
    run_deep_risk_enrichment,
    search_businesses,
)

logger = logging.getLogger(__name__)


class SupplierSearchView(APIView):
    """Proxy the Azure Maps search endpoint."""

    def get(self, request):
        serializer = SupplierSearchSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data

        payload = search_businesses(
            query=params.get('q'),
            industry=params.get('industry'),
            country=params.get('country') or None,
            city=params.get('city') or None,
            state=params.get('state') or None,
        )

        return Response(payload, status=status.HTTP_200_OK)


class SupplierAssessmentView(APIView):
    """Execute risk scoring, enrichment, and AI explanation."""

    def post(self, request):
        serializer = SupplierAssessmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        business = serializer.validated_data

        gleif_data = get_gleif_enrichment(business['name'])
        risk = compute_risk_score(business.get('azure_result'), gleif_data)

        azure_summary = {
            key: business.get(key)
            for key in ['name', 'address', 'city', 'state', 'country', 'latitude', 'longitude', 'score']
        }
        gleif_summary = gleif_data.get('enriched_entity') or {}

        explanation = generate_risk_explanation(
            risk['overall_score'],
            risk['factors'],
            azure_summary,
            gleif_summary,
        )

        response_payload = {
            'business': BusinessInfoSerializer(business).data,
            'risk_score': risk['overall_score'],
            'risk_factors': risk['factors'],
            'explanation': explanation,
            'azure_raw': business.get('azure_result'),
            'gleif_raw': gleif_data.get('raw_gleif_response'),
            'gleif_enriched': gleif_data.get('enriched_entity'),
            'gleif_request': gleif_data.get('request_metadata'),
            'risk_debug_payload': risk['debug_payload'],
        }

        logger.info('Risk assessment completed', extra={'business': business.get('name')})
        return Response(response_payload, status=status.HTTP_200_OK)


class SupplierDeepRiskView(APIView):
    """Execute the full deep-risk enrichment workflow against public datasets."""

    def post(self, request):
        serializer = SupplierDeepRiskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        business = serializer.validated_data

        azure_result = business.get('azure_result') or {}
        azure_address = azure_result.get('address') or {}

        city = business.get('city') or azure_address.get('municipality') or azure_address.get('localName')
        state = business.get('state') or azure_address.get('countrySubdivision')
        postal_code = business.get('postalCode') or azure_address.get('postalCode')
        country = business.get('country') or azure_address.get('countryCodeISO3') or azure_address.get('countryCode')
        county = business.get('county') or azure_address.get('countrySecondarySubdivision')

        supplier = SimpleNamespace(
            name=business.get('name'),
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
            county=county,
            lei=business.get('lei'),
        )

        data = run_deep_risk_enrichment(supplier)
        return Response(data, status=status.HTTP_200_OK)


@api_view(['POST'])
def enrich_supplier_with_gleif(request):
    """Use a selected Azure Maps business result to fetch matching GLEIF data."""

    serializer = SelectedAzureBusinessSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    azure_business = serializer.validated_data
    gleif_result = gleif_deep_lookup_from_azure_result(azure_business)

    payload = {
        'azure_business': azure_business,
        'gleif_raw': gleif_result.get('gleif_raw'),
        'gleif_pretty': gleif_result.get('gleif_pretty'),
        'error': gleif_result.get('error'),
    }

    logger.info('GLEIF enrichment completed', extra={'business': azure_business.get('name')})
    return Response(payload, status=status.HTTP_200_OK)
