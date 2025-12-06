"""Serializers for supplier search and assessment flows."""

from __future__ import annotations

from rest_framework import serializers


def _clean(value: str | None, *, upper: bool = False) -> str:
    if value is None:
        return ''
    cleaned = value.strip()
    return cleaned.upper() if upper else cleaned


class SupplierSearchSerializer(serializers.Serializer):
    q = serializers.CharField(max_length=255, required=False, allow_blank=True)
    industry = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    state = serializers.CharField(required=False, allow_blank=True)
    country = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        attrs['q'] = _clean(attrs.get('q'))
        attrs['industry'] = _clean(attrs.get('industry'))
        attrs['city'] = _clean(attrs.get('city'))
        attrs['state'] = _clean(attrs.get('state'))
        attrs['country'] = _clean(attrs.get('country'), upper=True)

        if not attrs['q'] and not attrs['industry']:
            raise serializers.ValidationError('Provide a business name or industry keyword.')
        return attrs


class BusinessInfoSerializer(serializers.Serializer):
    id = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(max_length=255)
    address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    state = serializers.CharField(required=False, allow_blank=True)
    country = serializers.CharField(required=False, allow_blank=True)
    postalCode = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)
    score = serializers.FloatField(required=False)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    website = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    azure_result = serializers.DictField(required=False)


class SupplierAssessmentSerializer(BusinessInfoSerializer):
    """Incoming data when the frontend requests a risk assessment."""

    azure_result = serializers.DictField(required=False)


class SupplierDeepRiskSerializer(SupplierAssessmentSerializer):
    """Serializer for running the deep risk enrichment pipeline."""

    county = serializers.CharField(required=False, allow_blank=True)
    lei = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class SelectedAzureBusinessSerializer(serializers.Serializer):
    """Serializer for accepting the full Azure POI payload from the frontend."""

    id = serializers.CharField(required=False, allow_blank=True)
    poi = serializers.DictField(required=False)
    address = serializers.DictField(required=False)
    name = serializers.CharField(required=False, allow_blank=True)

    def to_internal_value(self, data):  # type: ignore[override]
        if not isinstance(data, dict):
            raise serializers.ValidationError('Business payload must be a JSON object.')

        # Preserve the full Azure payload by merging validated and extra fields.
        known = {key: data.get(key) for key in self.fields if key in data}
        validated = super().to_internal_value(known)
        extras = {key: value for key, value in data.items() if key not in self.fields}
        validated.update(extras)
        return validated

    def validate(self, attrs):
        name = attrs.get('name') or (attrs.get('poi') or {}).get('name')
        if not name or not str(name).strip():
            raise serializers.ValidationError('A business name is required for GLEIF lookup.')
        return attrs
