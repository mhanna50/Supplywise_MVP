from django.urls import path

from .views import (
    SupplierAssessmentView,
    SupplierDeepRiskView,
    SupplierSearchView,
    enrich_supplier_with_gleif,
)

urlpatterns = [
    path('search/', SupplierSearchView.as_view(), name='supplier-search'),
    path('assess/', SupplierAssessmentView.as_view(), name='supplier-assess'),
    path('deep-risk/', SupplierDeepRiskView.as_view(), name='supplier-deep-risk'),
    path('enrich/', enrich_supplier_with_gleif, name='supplier-enrich'),
]
